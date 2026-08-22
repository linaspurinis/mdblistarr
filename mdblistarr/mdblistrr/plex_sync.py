import logging
import os
import traceback
from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError
from django.utils import timezone

from .models import Log, PlexInstance, PlexPosterState, PlexSyncRun
from .plex_api import PlexServerAPI
from .poster_overlay import render_badges
from .services import get_mdblistarr, reset_mdblistarr

logger = logging.getLogger(__name__)

PLEX_POSTER_PROVIDER = 4  # Log.provider code for this job

# Recently-released titles' scores/ratings move faster (still accumulating
# votes) and are more likely to be actively watched, so they're worth
# rechecking more often than a title from a decade ago. "Recent" = released
# this year or last year, by Plex's own `year` field (already returned for
# free in the library listing, so this costs nothing extra to check).
MDBLIST_RECHECK_INTERVAL_RECENT = timedelta(hours=24)
MDBLIST_RECHECK_INTERVAL_OLDER = timedelta(hours=48)
RECENT_YEAR_WINDOW = 1

MDBLIST_BATCH_SIZE = 200  # api.mdblist.com hard limit per batch lookup request
POSTER_CACHE_ROOT = Path(os.environ.get('MDBLISTARR_POSTER_CACHE_DIR', '/usr/src/db/plex_poster_cache'))
GUID_PROVIDER_PREFERENCE = ('imdb', 'tmdb', 'tvdb')


class PlexSyncCancelled(Exception):
    pass


def _save_log(status, text):
    Log.objects.create(date=timezone.now(), status=status, provider=PLEX_POSTER_PROVIDER, text=text)


def _check_cancelled(run):
    if run is None:
        return
    run.refresh_from_db(fields=['cancel_requested'])
    if run.cancel_requested:
        raise PlexSyncCancelled()


def _record_progress(run, *, processed=0, stamped=0, skipped=0, errors=0, current_title=None):
    if run is None:
        return
    run.processed_items += processed
    run.stamped += stamped
    run.skipped += skipped
    run.errors += errors
    fields = ['processed_items', 'stamped', 'skipped', 'errors']
    if current_title is not None:
        run.current_title = current_title
        fields.append('current_title')
    run.save(update_fields=fields)


def _cache_path(instance_id, rating_key):
    return POSTER_CACHE_ROOT / str(instance_id) / f"{rating_key}.jpg"


def _preferred_provider_and_id(guids):
    for provider in GUID_PROVIDER_PREFERENCE:
        if guids.get(provider):
            return provider, guids[provider]
    return None, None


def _lookup_media_info(mdblist_api, provider, media_type, ids):
    """Batch-resolve mdblist score/age rating. Returns {provider_id (str): media_info dict}."""
    result_map = {}
    for i in range(0, len(ids), MDBLIST_BATCH_SIZE):
        chunk = ids[i:i + MDBLIST_BATCH_SIZE]
        res = mdblist_api.get_media_info_batch(provider, media_type, chunk)
        if not isinstance(res, list):
            continue
        for entry in res:
            entry_ids = entry.get('ids') or {}
            key = entry_ids.get(provider)
            if key is not None:
                result_map[str(key)] = entry
    return result_map


def _extract_score_and_age(media_info):
    score = media_info.get('score')
    score = int(round(score)) if isinstance(score, (int, float)) else None

    # Common Sense Media's age_rating is a bare minimum-age number (e.g. "13");
    # normalize to "13+" so the badge always reads as "and up". Fall back to
    # the official certification (e.g. "PG-13", "TV-MA") as-is when no CSM
    # rating exists — those aren't minimum-age numbers, so no "+" is added.
    csm_age = media_info.get('age_rating')
    if csm_age not in (None, ''):
        digits = str(csm_age).strip().rstrip('+').strip()
        age_rating = f"{digits}+" if digits.isdigit() else str(csm_age).strip()
    else:
        certification = media_info.get('certification')
        age_rating = str(certification).strip() or None if certification else None

    return score, age_rating


def _recheck_interval(item):
    year = item.get('year')
    if year and year >= timezone.now().year - RECENT_YEAR_WINDOW:
        return MDBLIST_RECHECK_INTERVAL_RECENT
    return MDBLIST_RECHECK_INTERVAL_OLDER


def _needs_mdblist_check(item, state, now, instance):
    if not state:
        return True
    # Only gate on "is the poster still ours" when badges are actually being
    # stamped — with both badge toggles off, last_uploaded_thumb_key is never
    # set (there's no poster upload to set it), so this would otherwise always
    # read as a foreign change and force a full recheck every run.
    if instance.badge_score_enabled or instance.badge_age_rating_enabled:
        thumb_is_ours = bool(item['thumb']) and item['thumb'] == state.last_uploaded_thumb_key
        if not thumb_is_ours:
            return True
    if instance.sync_audience_rating_enabled and state.synced_audience_rating is None:
        return True  # rating sync just turned on; this item has never been rated by us
    stale = not state.mdblist_checked_at or (now - state.mdblist_checked_at) > _recheck_interval(item)
    return stale


def _poster_is_dirty(item, state, badge_score, badge_age):
    if badge_score is None and badge_age is None:
        return False
    if not state:
        return True
    if item['thumb'] != state.last_uploaded_thumb_key:
        return True  # foreign change (or first run) — needs a fresh stamp regardless
    return state.stamped_score != badge_score or state.stamped_age_rating != badge_age


def _original_poster_bytes(item, state):
    """
    Returns (bytes_or_None, is_from_cache). Only reuses the on-disk cached
    original when our own poster is still the one active on Plex (thumb
    matches what we uploaded) — otherwise the "original" must be re-fetched
    from Plex, since a foreign change means the art itself may be new.
    """
    if state and item['thumb'] == state.last_uploaded_thumb_key and state.original_poster_cache_path:
        cache_path = Path(state.original_poster_cache_path)
        if cache_path.exists():
            return cache_path.read_bytes(), True
        # Our poster is active but the cached original is gone — refuse to
        # treat Plex's current (already-stamped) image as a fresh original.
        return None, True
    return None, False


def _apply_item(plex, instance, section_id, media_type, item, state, badge_score, badge_age, target_plex_rating, poster_dirty, now):
    rating_key = item['rating_key']
    guids = item['guids']
    if state is None:
        state = PlexPosterState(plex_instance=instance, rating_key=rating_key)

    state.section_id = section_id
    state.section_type = media_type
    state.imdb_id = guids.get('imdb')
    state.tmdb_id = guids.get('tmdb')
    state.tvdb_id = guids.get('tvdb')
    state.title = item.get('title')

    had_error = False

    if poster_dirty:
        original_bytes, from_cache = _original_poster_bytes(item, state)
        cache_path = None
        if original_bytes is None and from_cache:
            # Active poster is ours but its cached source is missing; skip
            # rather than risk double-stamping an already-badged image.
            had_error = True
        elif original_bytes is None:
            if not item['thumb']:
                had_error = True
            else:
                original_bytes = plex.get_poster_bytes(item['thumb'])
                if not original_bytes:
                    had_error = True
                else:
                    cache_path = _cache_path(instance.id, rating_key)
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(original_bytes)
        else:
            cache_path = Path(state.original_poster_cache_path)

        if not had_error:
            stamped_bytes = render_badges(original_bytes, score=badge_score, age_rating=badge_age)
            if plex.upload_poster(rating_key, stamped_bytes):
                new_thumb = plex.get_item_thumb(rating_key) or ''
                state.stamped_score = badge_score
                state.stamped_age_rating = badge_age
                state.last_thumb_key = new_thumb
                state.last_uploaded_thumb_key = new_thumb
                state.original_poster_cache_path = str(cache_path)
                state.stamped_at = now
            else:
                had_error = True

    if target_plex_rating is not None:
        if state.original_audience_rating is None:
            state.original_audience_rating = item.get('audience_rating')
        if plex.set_audience_rating(section_id, media_type, rating_key, target_plex_rating, locked=True):
            state.synced_audience_rating = target_plex_rating
        else:
            had_error = True

    state.mdblist_checked_at = now
    state.save()
    return 'error' if had_error else 'updated'


def _sync_section(plex, mdblistarr, instance, section, run):
    section_id, media_type = section['id'], section['type']
    items = plex.get_section_items(section_id)
    if not items:
        return

    if run is not None:
        run.total_items += len(items)
        run.save(update_fields=['total_items'])

    states = {
        s.rating_key: s for s in PlexPosterState.objects.filter(
            plex_instance=instance, rating_key__in=[it['rating_key'] for it in items]
        )
    }

    now = timezone.now()
    needs_check = [it for it in items if _needs_mdblist_check(it, states.get(it['rating_key']), now, instance)]
    cheap_skip_count = len(items) - len(needs_check)
    if cheap_skip_count:
        _record_progress(run, processed=cheap_skip_count, skipped=cheap_skip_count)
    if not needs_check:
        return

    _check_cancelled(run)

    provider_groups = {}
    item_provider_id = {}
    for item in needs_check:
        provider, pid = _preferred_provider_and_id(item['guids'])
        if not provider:
            continue
        item_provider_id[item['rating_key']] = (provider, pid)
        provider_groups.setdefault(provider, []).append(pid)

    media_info_by_provider = {
        provider: _lookup_media_info(mdblistarr.mdblist, provider, media_type, ids)
        for provider, ids in provider_groups.items()
    }

    for item in needs_check:
        # Each item here already does real network I/O (mdblist was already
        # batched above; stamping/rating-sync does further Plex calls), so a
        # cheap per-item cancellation check adds negligible overhead and keeps
        # Cancel responsive even on small/medium libraries.
        _check_cancelled(run)

        rating_key = item['rating_key']
        provider_pid = item_provider_id.get(rating_key)
        if not provider_pid:
            _record_progress(run, processed=1, skipped=1, current_title=item.get('title'))
            continue
        provider, pid = provider_pid
        media_info = media_info_by_provider.get(provider, {}).get(str(pid))
        if not media_info:
            _record_progress(run, processed=1, skipped=1, current_title=item.get('title'))
            continue

        score, age_rating = _extract_score_and_age(media_info)
        badge_score = score if instance.badge_score_enabled else None
        badge_age = age_rating if instance.badge_age_rating_enabled else None
        rating_wanted = instance.sync_audience_rating_enabled and score is not None

        if badge_score is None and badge_age is None and not rating_wanted:
            _record_progress(run, processed=1, skipped=1, current_title=item.get('title'))
            continue

        state = states.get(rating_key)
        poster_dirty = _poster_is_dirty(item, state, badge_score, badge_age)
        target_plex_rating = round(score / 10, 1) if rating_wanted else None
        rating_dirty = rating_wanted and (not state or state.synced_audience_rating != target_plex_rating)

        if not poster_dirty and not rating_dirty:
            if state:
                state.mdblist_checked_at = now
                state.last_thumb_key = item['thumb']
                state.save(update_fields=['mdblist_checked_at', 'last_thumb_key', 'updated_at'])
            _record_progress(run, processed=1, skipped=1, current_title=item.get('title'))
            continue

        try:
            result = _apply_item(
                plex, instance, section_id, media_type, item, state,
                badge_score, badge_age, target_plex_rating if rating_dirty else None,
                poster_dirty, now,
            )
        except Exception:
            logger.error(f"Plex item update failed for rating_key={rating_key}: {traceback.format_exc()}")
            result = 'error'

        _record_progress(
            run, processed=1, current_title=item.get('title'),
            stamped=1 if result == 'updated' else 0,
            errors=1 if result == 'error' else 0,
        )


def sync_plex_posters(run=None):
    """
    `run` may be passed in already-created (e.g. by the view that spawned the
    background thread, so the PlexSyncRun row exists — and is visible to any
    concurrent status/start check — before the thread even starts running).
    When called without one (e.g. the cron task), it creates + single-flight
    guards its own run.
    """
    if run is None:
        if PlexSyncRun.objects.filter(status='running').exists():
            return {'response': 'AlreadyRunning'}
        try:
            run = PlexSyncRun.objects.create(status='running', started_at=timezone.now(), kind='sync')
        except IntegrityError:
            # Lost the race to another run that started between the check
            # above and this create — the DB-level partial unique constraint
            # (uniq_plexsyncrun_running) is the actual single-flight guard.
            return {'response': 'AlreadyRunning'}

    try:
        reset_mdblistarr()
        mdblistarr = get_mdblistarr()
        if mdblistarr.mdblist is None:
            _save_log(2, "MDBList API key not configured")
            run.status = 'error'
            run.error_message = 'MDBList API key not configured'
            run.finished_at = timezone.now()
            run.save()
            return {"response": "Missing API key"}

        instances = list(PlexInstance.objects.order_by('id'))
        if not instances:
            run.status = 'complete'
            run.finished_at = timezone.now()
            run.save()
            return {"response": "No Plex instances configured"}

        for instance in instances:
            _check_cancelled(run)
            try:
                plex = PlexServerAPI(instance_id=instance.id)
            except Exception:
                _save_log(2, f"{instance.name}: Failed to initialize Plex connection")
                continue

            library_ids = {lid for lid in (instance.library_ids or '').split(',') if lid.strip()}
            if not library_ids:
                continue

            sections = {s['id']: s for s in plex.get_sections() if s['id'] in library_ids}
            for section in sections.values():
                _check_cancelled(run)
                _sync_section(plex, mdblistarr, instance, section, run)

        run.status = 'complete'
        run.finished_at = timezone.now()
        run.save()
    except PlexSyncCancelled:
        run.status = 'cancelled'
        run.finished_at = timezone.now()
        run.save()
    except Exception:
        run.status = 'error'
        run.error_message = traceback.format_exc()[:2000]
        run.finished_at = timezone.now()
        run.save()
        _save_log(2, f'{traceback.format_exc()}')
        return {'response': 'Exception'}

    _save_log(1, f"Plex poster sync: updated={run.stamped} skipped={run.skipped} errors={run.errors} status={run.status}")
    return {"response": "Ok", "status": run.status, "stamped": run.stamped, "skipped": run.skipped, "error": run.errors}


def poster_states_in_scope():
    """
    PlexPosterState rows whose section is still selected in that instance's
    library_ids — the same population sync_plex_posters() would touch.
    reset_plex_posters() mirrors this scope since the two actions sit
    side-by-side in the UI and should behave symmetrically: reset only
    reverts what a sync would currently (re)touch, not every item mdblistarr
    has ever changed regardless of what's still selected.
    """
    queryset = PlexPosterState.objects.none()
    for instance in PlexInstance.objects.order_by('id'):
        library_ids = [lid for lid in (instance.library_ids or '').split(',') if lid.strip()]
        if not library_ids:
            continue
        queryset = queryset | PlexPosterState.objects.filter(plex_instance=instance, section_id__in=library_ids)
    return queryset


def _reset_item(plex, state):
    had_error = False

    if state.original_poster_cache_path:
        cache_path = Path(state.original_poster_cache_path)
        if cache_path.exists():
            if not plex.upload_poster(state.rating_key, cache_path.read_bytes()):
                had_error = True
        else:
            # Cached original is gone but Plex may still be showing our
            # badge-stamped poster. Treat this as an error and keep the state
            # row rather than deleting it — deleting here would make the next
            # sync treat the still-stamped image as a fresh "original" and
            # double-stamp it (see _original_poster_bytes's matching guard).
            had_error = True

    if state.synced_audience_rating is not None:
        # original_audience_rating is None when the item genuinely had no
        # rating before we touched it — restore to "unrated", not a
        # fabricated 0/10, by clearing the override entirely.
        restore_value = state.original_audience_rating if state.original_audience_rating is not None else ''
        if not plex.set_audience_rating(state.section_id, state.section_type, state.rating_key, restore_value, locked=False):
            had_error = True

    if not had_error:
        state.delete()
    return 'error' if had_error else 'reset'


def reset_plex_posters(run=None):
    """
    Reverts what mdblistarr has changed (posters and, if it was enabled,
    audience ratings) back to what Plex had before, using the same cached
    originals the sync job already keeps for its own dedup logic. Scoped to
    the same items sync_plex_posters() would currently touch — i.e. only
    currently-selected libraries — since the two actions sit next to each
    other in the UI and should behave symmetrically (see poster_states_in_scope).

    See sync_plex_posters() for the `run` parameter's purpose.
    """
    if run is None:
        if PlexSyncRun.objects.filter(status='running').exists():
            return {'response': 'AlreadyRunning'}
        try:
            run = PlexSyncRun.objects.create(status='running', started_at=timezone.now(), kind='reset')
        except IntegrityError:
            # Lost the race to another run that started between the check
            # above and this create — the DB-level partial unique constraint
            # (uniq_plexsyncrun_running) is the actual single-flight guard.
            return {'response': 'AlreadyRunning'}

    try:
        states = list(poster_states_in_scope().select_related('plex_instance'))
        run.total_items = len(states)
        run.save(update_fields=['total_items'])

        if not states:
            run.status = 'complete'
            run.finished_at = timezone.now()
            run.save()
            return {'response': 'Ok', 'status': run.status, 'reset': 0, 'error': 0}

        plex_by_instance = {}

        for state in states:
            _check_cancelled(run)
            instance = state.plex_instance
            plex = plex_by_instance.get(instance.id)
            if plex is None:
                try:
                    plex = PlexServerAPI(instance_id=instance.id)
                except Exception:
                    plex = False
                plex_by_instance[instance.id] = plex

            if not plex:
                _record_progress(run, processed=1, errors=1, current_title=state.title)
                continue

            try:
                result = _reset_item(plex, state)
            except Exception:
                logger.error(f"Plex poster reset failed for rating_key={state.rating_key}: {traceback.format_exc()}")
                result = 'error'

            _record_progress(
                run, processed=1, current_title=state.title,
                stamped=1 if result == 'reset' else 0,
                errors=1 if result == 'error' else 0,
            )

        run.status = 'complete'
        run.finished_at = timezone.now()
        run.save()
    except PlexSyncCancelled:
        run.status = 'cancelled'
        run.finished_at = timezone.now()
        run.save()
    except Exception:
        run.status = 'error'
        run.error_message = traceback.format_exc()[:2000]
        run.finished_at = timezone.now()
        run.save()
        _save_log(2, f'{traceback.format_exc()}')
        return {'response': 'Exception'}

    _save_log(1, f"Plex poster reset: reset={run.stamped} errors={run.errors} status={run.status}")
    return {"response": "Ok", "status": run.status, "reset": run.stamped, "error": run.errors}
