from django.utils import timezone
from django.tasks import task
from django_scheduled_tasks import cron_task
from .connect import Connect
import time
import json
import random
import traceback
from .models import Log, InstanceChangeLog, RadarrInstance, SonarrInstance, Preferences
from .services import get_mdblistarr
from .arr import SonarrAPI
from .arr import RadarrAPI

def save_log(provider, status, text):
    log = Log()
    log.date = timezone.now()
    log.provider = provider
    log.status = status
    log.text = text
    log.save()

def post_radarr_payload():
    try:
        time.sleep(random.uniform(0.0, 10800.0))
        mdblistarr = get_mdblistarr()
        if mdblistarr.mdblist is None:
            save_log(1, 2, "MDBList API key not configured")
            return {"response": "Missing API key"}
        radarr_api = RadarrAPI()
        movies = radarr_api.get_movies()
        exclusions = radarr_api.get_exclusions()

        provider = 1 # Radarr JSON POST

        # Avoid sending an "empty" sync when Radarr is unreachable (can accidentally wipe state server-side).
        if isinstance(movies, dict) and movies.get('error'):
            save_log(provider, 2, f"{radarr_api.name}: Radarr /movie request failed: {movies}")
            return {"response": "RadarrError"}
        if isinstance(movies, list) and len(movies) == 1 and isinstance(movies[0], dict) and movies[0].get('result'):
            save_log(provider, 2, f"{radarr_api.name}: Radarr /movie request failed: {movies[0].get('result')}")
            return {"response": "RadarrError"}
        if not isinstance(movies, list):
            save_log(provider, 2, f"{radarr_api.name}: Radarr /movie unexpected response type={type(movies)} payload={str(movies)[:500]}")
            return {"response": "RadarrError"}

        records_by_tmdb = {}

        # Library state (downloaded/missing).
        for movie in movies if isinstance(movies, list) else []:
            if not isinstance(movie, dict):
                continue
            tmdb_id = movie.get('tmdbId')
            if not tmdb_id:
                continue

            has_file = movie.get('hasFile')
            if has_file is True:
                records_by_tmdb[tmdb_id] = {'tmdb': tmdb_id, 'exists': True}
            elif has_file is False:
                records_by_tmdb[tmdb_id] = {'tmdb': tmdb_id, 'exists': False}
            else:
                # Fallback: older/odd responses. Treat presence in Radarr as "exists".
                records_by_tmdb[tmdb_id] = {'tmdb': tmdb_id, 'exists': True}

        # Import List Exclusions -> mark excluded. Include excluded even if not in library.
        excluded_count = 0
        if isinstance(exclusions, dict) and exclusions.get('error'):
            save_log(provider, 2, f"{radarr_api.name}: Radarr /exclusions request failed: {exclusions}")
            exclusions = []
        elif isinstance(exclusions, list) and len(exclusions) == 1 and isinstance(exclusions[0], dict) and exclusions[0].get('result'):
            save_log(provider, 2, f"{radarr_api.name}: Radarr /exclusions request failed: {exclusions[0].get('result')}")
            exclusions = []
        elif not isinstance(exclusions, list):
            save_log(provider, 2, f"{radarr_api.name}: Radarr /exclusions unexpected response type={type(exclusions)} payload={str(exclusions)[:500]}")
            exclusions = []

        for ex in exclusions if isinstance(exclusions, list) else []:
            if not isinstance(ex, dict):
                continue
            tmdb_id = ex.get('tmdbId') or ex.get('tmdbid')
            if not tmdb_id:
                continue
            rec = records_by_tmdb.get(tmdb_id, {'tmdb': tmdb_id})
            if not rec.get('excluded'):
                excluded_count += 1
            rec['excluded'] = True
            records_by_tmdb[tmdb_id] = rec

        records = list(records_by_tmdb.values())
        total_records = len(records)
        json_payload = {'radarr': records}

        res = mdblistarr.mdblist.post_arr_payload(json_payload)

        if res.get('response') == 'Ok':
            save_log(provider, 1, f'{radarr_api.name}: Uploaded {total_records} records to MDBList.com (excluded={excluded_count})')
        else:
            save_log(provider, 2, f'Upload records to MDBList.com Failed: {res}')
            return res

        sync_library_pref = Preferences.objects.filter(name='sync_library_status').first()
        if sync_library_pref and sync_library_pref.value == '1':
            collection_add = [{'ids': {'tmdb': rec['tmdb']}} for rec in records if rec.get('exists')]
            collection_remove = [{'ids': {'tmdb': rec['tmdb']}} for rec in records if rec.get('exists') is False]

            chunk_size = 250
            total_added = 0
            for i in range(0, len(collection_add), chunk_size):
                chunk = collection_add[i:i + chunk_size]
                add_res = mdblistarr.mdblist.post_collection({'movies': chunk})
                if isinstance(add_res, dict) and add_res.get('error'):
                    save_log(provider, 2, f'{radarr_api.name}: Collection add failed: {add_res}')
                    break
                total_added += add_res.get('updated', {}).get('movies', 0) if isinstance(add_res, dict) else 0
            if total_added:
                save_log(provider, 1, f'{radarr_api.name}: Synced {total_added} movies to MDBList collection')

            total_removed = 0
            for i in range(0, len(collection_remove), chunk_size):
                chunk = collection_remove[i:i + chunk_size]
                rm_res = mdblistarr.mdblist.post_collection_remove({'movies': chunk})
                if isinstance(rm_res, dict) and rm_res.get('error'):
                    save_log(provider, 2, f'{radarr_api.name}: Collection remove failed: {rm_res}')
                    break
                total_removed += rm_res.get('removed', {}).get('movies', 0) if isinstance(rm_res, dict) else 0
            if total_removed:
                save_log(provider, 1, f'{radarr_api.name}: Removed {total_removed} movies from MDBList collection')

        return res
    except:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return {'response': 'Exception'}

@cron_task(cron_schedule="11 10 * * *")
@task
def post_radarr_payload_task():
    return post_radarr_payload()

def post_sonarr_payload():
    try:
        time.sleep(random.uniform(0.0, 10800.0))
        mdblistarr = get_mdblistarr()
        if mdblistarr.mdblist is None:
            save_log(2, 2, "MDBList API key not configured")
            return {"response": "Missing API key"}
        sonarr_api = SonarrAPI()
        series = sonarr_api.get_series()
        exclusions = sonarr_api.get_import_list_exclusions()

        provider = 2 # Sonarr JSON POST

        # Avoid sending an "empty" sync when Sonarr is unreachable (can accidentally wipe state server-side).
        if isinstance(series, dict) and series.get('error'):
            save_log(provider, 2, f"{sonarr_api.name}: Sonarr /series request failed: {series}")
            return {"response": "SonarrError"}
        if isinstance(series, list) and len(series) == 1 and isinstance(series[0], dict) and series[0].get('result'):
            save_log(provider, 2, f"{sonarr_api.name}: Sonarr /series request failed: {series[0].get('result')}")
            return {"response": "SonarrError"}
        if not isinstance(series, list):
            save_log(provider, 2, f"{sonarr_api.name}: Sonarr /series unexpected response type={type(series)} payload={str(series)[:500]}")
            return {"response": "SonarrError"}

        records_by_tvdb = {}

        # Library state (downloaded/missing).
        for show in series if isinstance(series, list) else []:
            if not isinstance(show, dict):
                continue
            tvdb_id = show.get('tvdbId')
            if not tvdb_id:
                continue

            # Prefer series-level statistics when present.
            # We consider "downloaded" if there is at least 1 episode file.
            episode_file_count = None
            stats = show.get('statistics') if isinstance(show.get('statistics'), dict) else None
            if stats is not None and isinstance(stats.get('episodeFileCount'), int):
                episode_file_count = stats.get('episodeFileCount')

            # Fallback: sum season statistics.
            if episode_file_count is None and isinstance(show.get('seasons'), list):
                total = 0
                found_any = False
                for season in show['seasons']:
                    if not isinstance(season, dict):
                        continue
                    s = season.get('statistics') if isinstance(season.get('statistics'), dict) else None
                    if s is None:
                        continue
                    if isinstance(s.get('episodeFileCount'), int):
                        total += s.get('episodeFileCount')
                        found_any = True
                if found_any:
                    episode_file_count = total

            if episode_file_count is None:
                # Can't infer reliably; treat presence in Sonarr as "exists".
                records_by_tvdb[tvdb_id] = {'tvdb': tvdb_id, 'exists': True}
            elif episode_file_count > 0:
                records_by_tvdb[tvdb_id] = {'tvdb': tvdb_id, 'exists': True}
            else:
                records_by_tvdb[tvdb_id] = {'tvdb': tvdb_id, 'exists': False}

        # Import List Exclusions -> mark excluded. Include excluded even if not in library.
        excluded_count = 0
        if isinstance(exclusions, dict) and exclusions.get('error'):
            save_log(provider, 2, f"{sonarr_api.name}: Sonarr /importlistexclusion request failed: {exclusions}")
            exclusions = []
        elif isinstance(exclusions, list) and len(exclusions) == 1 and isinstance(exclusions[0], dict) and exclusions[0].get('result'):
            save_log(provider, 2, f"{sonarr_api.name}: Sonarr /importlistexclusion request failed: {exclusions[0].get('result')}")
            exclusions = []
        elif not isinstance(exclusions, list):
            save_log(provider, 2, f"{sonarr_api.name}: Sonarr /importlistexclusion unexpected response type={type(exclusions)} payload={str(exclusions)[:500]}")
            exclusions = []

        for ex in exclusions if isinstance(exclusions, list) else []:
            if not isinstance(ex, dict):
                continue
            tvdb_id = ex.get('tvdbId') or ex.get('tvdbid')
            if not tvdb_id:
                continue
            rec = records_by_tvdb.get(tvdb_id, {'tvdb': tvdb_id})
            if not rec.get('excluded'):
                excluded_count += 1
            rec['excluded'] = True
            records_by_tvdb[tvdb_id] = rec

        records = list(records_by_tvdb.values())
        total_records = len(records)
        json_payload = {'sonarr': records}

        res = mdblistarr.mdblist.post_arr_payload(json_payload)
        if res.get('response') == 'Ok':
            save_log(provider, 1, f'{sonarr_api.name}: Uploaded {total_records} records to MDBList.com (excluded={excluded_count})')
        else:
            save_log(provider, 2, f'Upload records to MDBList.com Failed: {res}')
            return res

        sync_library_pref = Preferences.objects.filter(name='sync_library_status').first()
        if sync_library_pref and sync_library_pref.value == '1':
            # Build season-level collection payloads from already-fetched series data.
            # Each show in Sonarr includes per-season statistics, so no extra API calls needed.
            collection_add = []
            collection_remove = []

            for show in series if isinstance(series, list) else []:
                if not isinstance(show, dict):
                    continue
                tvdb_id = show.get('tvdbId')
                if not tvdb_id:
                    continue

                seasons_with_files = []
                for season in show.get('seasons') or []:
                    if not isinstance(season, dict):
                        continue
                    season_num = season.get('seasonNumber')
                    if season_num is None:
                        continue
                    s_stats = season.get('statistics') if isinstance(season.get('statistics'), dict) else {}
                    if isinstance(s_stats.get('episodeFileCount'), int) and s_stats['episodeFileCount'] > 0:
                        seasons_with_files.append({'number': season_num})

                if seasons_with_files:
                    collection_add.append({'ids': {'tvdb': tvdb_id}, 'seasons': seasons_with_files})
                elif records_by_tvdb.get(tvdb_id, {}).get('exists') is False:
                    collection_remove.append({'ids': {'tvdb': tvdb_id}})

            chunk_size = 250
            total_shows, total_seasons = 0, 0
            for i in range(0, len(collection_add), chunk_size):
                chunk = collection_add[i:i + chunk_size]
                add_res = mdblistarr.mdblist.post_collection({'shows': chunk})
                if isinstance(add_res, dict) and add_res.get('error'):
                    save_log(provider, 2, f'{sonarr_api.name}: Collection add failed: {add_res}')
                    break
                updated = add_res.get('updated', {}) if isinstance(add_res, dict) else {}
                total_shows += updated.get('shows', 0)
                total_seasons += updated.get('seasons', 0)
            if total_shows or total_seasons:
                save_log(provider, 1, f'{sonarr_api.name}: Synced collection (shows={total_shows} seasons={total_seasons})')

            total_removed = 0
            for i in range(0, len(collection_remove), chunk_size):
                chunk = collection_remove[i:i + chunk_size]
                rm_res = mdblistarr.mdblist.post_collection_remove({'shows': chunk})
                if isinstance(rm_res, dict) and rm_res.get('error'):
                    save_log(provider, 2, f'{sonarr_api.name}: Collection remove failed: {rm_res}')
                    break
                total_removed += rm_res.get('removed', {}).get('shows', 0) if isinstance(rm_res, dict) else 0
            if total_removed:
                save_log(provider, 1, f'{sonarr_api.name}: Removed {total_removed} shows from MDBList collection')

        return res
    except:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return {'response': 'Exception'}

@cron_task(cron_schedule="11 11 * * *")
@task
def post_sonarr_payload_task():
    return post_sonarr_payload()

def get_mdblist_queue_to_arr():
    provider = 0  # Queue Sync
    try:
        time.sleep(random.uniform(0.0, 36.0))
        mdblistarr = get_mdblistarr()
        if mdblistarr.mdblist is None:
            save_log(provider, 2, "MDBList API key not configured")
            return {"result": 400, "error": "mdblist_apikey not configured"}

        queue_resp = mdblistarr.mdblist.get_mdblist_queue()

        # The MDBList queue endpoint usually returns a list of items, but in some
        # cases we can get a dict (error wrapper, rate limit, etc) or a JSON string.
        queue_items = None
        if isinstance(queue_resp, list):
            queue_items = queue_resp
        elif isinstance(queue_resp, dict):
            for key in ("queue", "results", "data", "items"):
                if isinstance(queue_resp.get(key), list):
                    queue_items = queue_resp[key]
                    break

            # If this is an error/traceback wrapper, stop early and log it.
            if queue_items is None:
                save_log(provider, 2, f"MDBList queue unexpected response (dict): {str(queue_resp)[:1000]}")
                return {"result": 502, "error": "unexpected_queue_response"}
        elif isinstance(queue_resp, str):
            try:
                decoded = json.loads(queue_resp)
            except Exception:
                save_log(provider, 2, f"MDBList queue unexpected response (str): {queue_resp[:500]}")
                return {"result": 502, "error": "unexpected_queue_response"}

            if isinstance(decoded, list):
                queue_items = decoded
            elif isinstance(decoded, dict):
                for key in ("queue", "results", "data", "items"):
                    if isinstance(decoded.get(key), list):
                        queue_items = decoded[key]
                        break
                if queue_items is None:
                    save_log(provider, 2, f"MDBList queue unexpected decoded response (dict): {str(decoded)[:1000]}")
                    return {"result": 502, "error": "unexpected_queue_response"}
            else:
                save_log(provider, 2, f"MDBList queue unexpected decoded response (type={type(decoded)}): {decoded}")
                return {"result": 502, "error": "unexpected_queue_response"}
        else:
            save_log(provider, 2, f"MDBList queue unexpected response type={type(queue_resp)}: {queue_resp}")
            return {"result": 502, "error": "unexpected_queue_response"}

        for item in queue_items:
            if not isinstance(item, dict):
                save_log(provider, 2, f"Skipping unexpected queue item type={type(item)}: {str(item)[:500]}")
                continue

            mediatype = item.get("mediatype")
            if mediatype is None:
                save_log(provider, 2, f"Skipping queue item missing 'mediatype': {item}")
                continue

            if mediatype == 'movie':
                provider = 1
                instance_id = item.get('instanceid')
                movie_request_json = {
                    "title": item['title'],
                    "tmdbid": item['tmdbid'],
                    "monitored": True, 
                    "addOptions": {"searchForMovie": True},
                    "qualityProfileId": mdblistarr.get_radarr_quality_profile(instance_id),
                    "rootFolderPath": mdblistarr.get_radarr_root_folder(instance_id)
                }

                radarr_api = RadarrAPI(instance_id=instance_id)
                res = radarr_api.post_movie(movie_request_json)
                if isinstance(res, list):
                    if res[0].get('errorMessage'):
                        msg = res[0].get('errorMessage') or ""
                        # Treat "already added" as a non-error and trigger a search instead.
                        if 'already been added' in msg.lower():
                            search_res = radarr_api.trigger_movie_search(item.get('tmdbid'))
                            if isinstance(search_res, dict) and search_res.get("error") == "movie_not_found":
                                save_log(provider, 2, f"Movie already exists in Radarr but could not resolve by tmdbid for search: {item['title']} (tmdbid={item.get('tmdbid')}).")
                            elif isinstance(search_res, dict) and search_res.get("error"):
                                save_log(provider, 2, f"Movie already exists in Radarr; search trigger failed: {item['title']}. {search_res}")
                            else:
                                save_log(provider, 1, f"Movie already exists in Radarr; triggered search: {item['title']}.")
                        else:
                            save_log(provider, 2, f"Error adding movie to Radarr: {item['title']}. {msg}.")
                    else:
                        save_log(provider, 2, f"Error posting movie to Radarr: {item['title']}. Raw response: {res}")
                        print(f"Error posting movie to Radarr: {item['title']}. Raw response: {res}")  # Print to console
                        # save_log(provider, 2, f"Error posting movie to Radarr")
                elif res.get('title'):
                    save_log(provider, 1, f"Added movie to Radarr: {item['title']}.")
                elif res.get('errorMessage'):
                    msg = res.get('errorMessage') or ""
                    if 'already been added' in msg.lower():
                        search_res = radarr_api.trigger_movie_search(item.get('tmdbid'))
                        if isinstance(search_res, dict) and search_res.get("error") == "movie_not_found":
                            save_log(provider, 2, f"Movie already exists in Radarr but could not resolve by tmdbid for search: {item['title']} (tmdbid={item.get('tmdbid')}).")
                        elif isinstance(search_res, dict) and search_res.get("error"):
                            save_log(provider, 2, f"Movie already exists in Radarr; search trigger failed: {item['title']}. {search_res}")
                        else:
                            save_log(provider, 1, f"Movie already exists in Radarr; triggered search: {item['title']}.")
                    else:
                        save_log(provider, 2, f"Error posting movie to Radarr: {item['title']}. {msg}")
                else:
                    # Log the full response for debugging
                    save_log(provider, 2, f"Error posting movie to Radarr: {item['title']}. Raw response: {res}")
                    print(f"Error posting movie to Radarr: {item['title']}. Raw response: {res}")  # Print to console
                    # save_log(provider, 2, f"Error posting movie to Radarr")
            elif mediatype == 'show':
                provider = 2
                instance_id = item.get('instanceid')
                show_request_json = {
                    "title": item['title'],
                    "tvdbid": item['tvdbid'],
                    "monitored": True, 
                    "addOptions": {"searchForMissingEpisodes": True},
                    "qualityProfileId": mdblistarr.get_sonarr_quality_profile(instance_id),
                    "rootFolderPath": mdblistarr.get_sonarr_root_folder(instance_id)
                }

                sonarr_api = SonarrAPI(instance_id=instance_id)
                res = sonarr_api.post_show(show_request_json)
                if isinstance(res, list):
                    if res[0].get('errorMessage'):
                        save_log(provider, 2, f"Error adding show to Sonarr: {item['title']}. {res[0]['errorMessage']}")
                    else:
                        save_log(provider, 2, f"Error posting show to Sonarr: {item['title']}. Raw response: {res}")
                        print(f"Error posting show to Sonarr: {item['title']}. Raw response: {res}")  # Print to console
                        # save_log(provider, 2, f"Error posting show to Sonarr")
                elif res.get('title'):
                    save_log(provider, 1, f"Added show to Sonarr {item['title']}.")
                elif res.get('errorMessage'):
                    save_log(provider, 2, f"Error posting show to Sonarr: {item['title']}. {res['errorMessage']}")
                else:
                    # Log the full response for debugging
                    save_log(provider, 2, f"Error posting show to Sonarr: {item['title']}. Raw response: {res}")
                    print(f"Error posting show to Sonarr: {item['title']}. Raw response: {res}")  # Print to console
                    # save_log(provider, 2, f"Error posting show to Sonarr")
            else:
                save_log(provider, 2, f"Skipping queue item with unknown mediatype={mediatype}: {item}")
    except Exception:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return {'result': 500}
    
    return {'result': 200}

@cron_task(cron_schedule="*/5 * * * *")
@task
def get_mdblist_queue_to_arr_task():
    return get_mdblist_queue_to_arr()

def process_instance_changes():
    provider = 3  # Instance Change Log
    try:
        logs = InstanceChangeLog.objects.filter(processed=False).order_by('timestamp')

        if not logs.exists():
            return {"response": "Log is empty"}

        time.sleep(random.uniform(0.0, 36.0))

        radarr_instances = RadarrInstance.objects.all()
        sonarr_instances = SonarrInstance.objects.all()
        
        json_payload = {
            "instances": {
                "radarr": [
                    {
                        "instance_id": radarr.id,
                        "instance_name": radarr.name,
                    } for radarr in radarr_instances
                ],
                "sonarr": [
                    {
                        "instance_id": sonarr.id,
                        "instance_name": sonarr.name,
                    } for sonarr in sonarr_instances
                ]
            }
        }
        
        if not radarr_instances and not sonarr_instances:
            logs.update(processed=True)
            return {"response": "No instances to sync"}
            
        mdblistarr = get_mdblistarr()
        if mdblistarr.mdblist is None:
            save_log(provider, 2, "MDBList API key not configured")
            return {"response": "Missing API key"}
        res = mdblistarr.mdblist.post_arr_changes(json_payload)
        
        if res.get('response') == 'Ok':
            logs.update(processed=True)
            save_log(provider, 1, f'Configuration uploaded to MDBList.com')
            return res
        else:
            save_log(provider, 2, f'Configuration upload to MDBList.com Failed: {res}')
            return res
    except Exception as e:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return {'result': 500}

@cron_task(cron_schedule="*/15 * * * *")
@task
def process_instance_changes_task():
    return process_instance_changes()
