import logging
import os
import traceback
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from .models import Log, PlexInstance, PlexPosterState, PlexSyncRun
from .plex_api import PlexServerAPI
from .poster_overlay import render_badges
from .services import get_mdblistarr, reset_mdblistarr

logger = logging.getLogger(__name__)

PLEX_POSTER_PROVIDER = 4  # Log.provider code for this job
MDBLIST_RECHECK_INTERVAL = timedelta(hours=24)
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


def _needs_mdblist_check(item, state, now):
    if not state:
        return True
    thumb_is_ours = bool(item['thumb']) and item['thumb'] == state.last_uploaded_thumb_key
    if not thumb_is_ours:
        return True
    stale = not state.mdblist_checked_at or (now - state.mdblist_checked_at) > MDBLIST_RECHECK_INTERVAL
    return stale


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


def _stamp_item(plex, instance, section_id, media_type, item, state, score, age_rating, now):
    rating_key = item['rating_key']
    guids = item['guids']

    original_bytes, from_cache = _original_poster_bytes(item, state)
    if original_bytes is None:
        if from_cache:
            # Active poster is ours but its cached source is missing; skip
            # rather than risk double-stamping an already-badged image.
            return 'error'
        if not item['thumb']:
            return 'error'
        original_bytes = plex.get_poster_bytes(item['thumb'])
        if not original_bytes:
            return 'error'
        cache_path = _cache_path(instance.id, rating_key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(original_bytes)
    else:
        cache_path = Path(state.original_poster_cache_path)

    stamped_bytes = render_badges(original_bytes, score=score, age_rating=age_rating)
    if not plex.upload_poster(rating_key, stamped_bytes):
        return 'error'

    new_thumb = plex.get_item_thumb(rating_key) or ''

    PlexPosterState.objects.update_or_create(
        plex_instance=instance,
        rating_key=rating_key,
        defaults={
            'section_id': section_id,
            'section_type': media_type,
            'imdb_id': guids.get('imdb'),
            'tmdb_id': guids.get('tmdb'),
            'tvdb_id': guids.get('tvdb'),
            'title': item.get('title'),
            'stamped_score': score,
            'stamped_age_rating': age_rating,
            'last_thumb_key': new_thumb,
            'last_uploaded_thumb_key': new_thumb,
            'original_poster_cache_path': str(cache_path),
            'mdblist_checked_at': now,
            'stamped_at': now,
        },
    )
    return 'stamped'


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
    needs_check = [it for it in items if _needs_mdblist_check(it, states.get(it['rating_key']), now)]
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
        # batched above; stamping does an image download/upload), so a cheap
        # per-item cancellation check adds negligible overhead and keeps
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
        if not instance.badge_score_enabled:
            score = None
        if not instance.badge_age_rating_enabled:
            age_rating = None
        if score is None and age_rating is None:
            _record_progress(run, processed=1, skipped=1, current_title=item.get('title'))
            continue

        state = states.get(rating_key)
        if state and item['thumb'] == state.last_uploaded_thumb_key \
                and state.stamped_score == score and state.stamped_age_rating == age_rating:
            state.mdblist_checked_at = now
            state.last_thumb_key = item['thumb']
            state.save(update_fields=['mdblist_checked_at', 'last_thumb_key', 'updated_at'])
            _record_progress(run, processed=1, skipped=1, current_title=item.get('title'))
            continue

        try:
            result = _stamp_item(plex, instance, section_id, media_type, item, state, score, age_rating, now)
        except Exception:
            logger.error(f"Plex poster stamp failed for rating_key={rating_key}: {traceback.format_exc()}")
            result = 'error'

        _record_progress(
            run, processed=1, current_title=item.get('title'),
            stamped=1 if result == 'stamped' else 0,
            skipped=1 if result == 'skipped' else 0,
            errors=1 if result == 'error' else 0,
        )


def sync_plex_posters():
    if PlexSyncRun.objects.filter(status='running').exists():
        return {'response': 'AlreadyRunning'}

    run = PlexSyncRun.objects.create(status='running', started_at=timezone.now())

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

    _save_log(1, f"Plex poster sync: stamped={run.stamped} skipped={run.skipped} errors={run.errors} status={run.status}")
    return {"response": "Ok", "status": run.status, "stamped": run.stamped, "skipped": run.skipped, "error": run.errors}
