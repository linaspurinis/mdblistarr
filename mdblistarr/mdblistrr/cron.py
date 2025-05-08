from django.http import JsonResponse
from django.utils import timezone
from .connect import Connect
import time
import json
import random
import traceback
from .models import Log, InstanceChangeLog, RadarrInstance, SonarrInstance
from .views import MDBListarr
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
        time.sleep(random.uniform(0.0, 3600.0))
        mdblistarr = MDBListarr()
        radarr_api = RadarrAPI()
        movies = radarr_api.get_movies()

        provider = 1 # Radarr JSON POST

        json = []
        for movie in movies:
            if movie.get('tmdbId'):
                exists = None
                if movie['hasFile']:
                    exists = True
                elif movie['monitored']:
                    exists = False
                if exists is not None:
                    json.append({'exists':exists, 'tmdb':movie.get('tmdbId')})
        total_records = len(json)
        json_payload = {'radarr': json}

        res = mdblistarr.mdblist.post_arr_payload(json_payload)

        if res.get('response') == 'Ok':
            save_log(provider, 1, f'{radarr_api.name}: Uploaded {total_records} records to MDBList.com')
            return JsonResponse(res)
        else:
            save_log(provider, 2, f'Upload records to MDBList.com Failed: {res}')
            return JsonResponse(res)
    except:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return JsonResponse({'response': 'Exception'})

def post_sonarr_payload():
    try:
        time.sleep(random.uniform(0.0, 3600.0))
        mdblistarr = MDBListarr()
        sonarr_api = SonarrAPI()
        series = sonarr_api.get_series()

        provider = 2 # Sonarr JSON POST

        json = []
        for show in series:
            if show.get('tvdbId'):
                exists = None
                if show.get('seasons'):
                    for season in show['seasons']:
                        if season.get('statistics', {}).get('percentOfEpisodes') == 100:
                            exists = True  # At least one season is downloaded 100%
                elif show['monitored']:
                    exists = False
                if exists is not None:
                    json.append({'exists':exists, 'tvdb':show.get('tvdbId')})
        total_records = len(json)
        json_payload = {'sonarr': json}

        res = mdblistarr.mdblist.post_arr_payload(json_payload)
        if res.get('response') == 'Ok':
            save_log(provider, 1, f'{sonarr_api.name}: Uploaded {total_records} records to MDBList.com')
            return JsonResponse(res)
        else:
            save_log(provider, 2, f'Upload records to MDBList.com Failed: {res}')
            return JsonResponse(res)
    except:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return JsonResponse({'response': 'Exception'})

def get_mdblist_queue_to_arr():

    try:
        time.sleep(random.uniform(0.0, 36.0))
        mdblistarr = MDBListarr()
        queue = mdblistarr.mdblist.get_mdblist_queue()

        for item in queue:
            if item['mediatype'] == 'movie':
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
                        save_log(provider, 2, f"Error adding movie to Radarr: {item['title']}. {res[0]['errorMessage']}.")
                    else:
                        save_log(provider, 2, f"Error posting movie to Radarr")
                elif res.get('title'):
                    save_log(provider, 1, f"Added movie to Radarr: {item['title']}.")
                elif res.get('errorMessage'):
                    save_log(provider, 2, f"Error posting show to Radarr: {item['title']}. {res['errorMessage']}")
                else:
                    save_log(provider, 2, f"Error posting movie to Radarr")
            elif item['mediatype'] == 'show':
                provider = 2
                instanceid = item.get('instanceid')
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
                        save_log(provider, 2, f"Error posting show to Sonarr")
                elif res.get('title'):
                    save_log(provider, 1, f"Added show to Sonarr {item['title']}.")
                elif res.get('errorMessage'):
                    save_log(provider, 2, f"Error posting show to Sonarr: {item['title']}. {res['errorMessage']}")
                else:
                    save_log(provider, 2, f"Error posting show to Sonarr")
    except:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return JsonResponse({'result': 500})
    
    return JsonResponse({'result': 200})

def process_instance_changes():
    try:
        provider = 3  # Instance Change Log
        logs = InstanceChangeLog.objects.filter(processed=False).order_by('timestamp')

        if not logs.exists():
            return JsonResponse({"response": "Log is empty"})

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
            return JsonResponse({"response": "No instances to sync"})
            
        mdblistarr = MDBListarr()
        res = mdblistarr.mdblist.post_arr_changes(json_payload)
        
        if res.get('response') == 'Ok':
            logs.update(processed=True)
            save_log(provider, 1, f'Configuration uploaded to MDBList.com')
            return JsonResponse(res)
        else:
            save_log(provider, 2, f'Configuration upload to MDBList.com Failed: {res}')
            return JsonResponse(res)
    except Exception as e:
        save_log(provider, 2, f'{traceback.format_exc()}')
        return JsonResponse({'result': 500})

