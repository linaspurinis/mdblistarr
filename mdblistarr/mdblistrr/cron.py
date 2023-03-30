from django.http import JsonResponse
from django.utils import timezone
from .connect import Connect
import time
import random
import traceback
from .models import Log, RadarrDestinations
from .views import MDBListarr
import ast

OK = 1
WARNING = 2
ERROR = 3

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
        movies = mdblistarr.radarr.get_movies()

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
        print(res)
        if res['response'] == 'Ok':
            save_log(provider, OK, f'Uploaded {total_records} records to MDBList.com')
            return JsonResponse(res)
        else:
            save_log(provider, WARNING, f'Upload records to MDBList.com Failed: {res}')
            return JsonResponse(res)
    except:
        save_log(provider, ERROR, f'{traceback.format_exc()}')
        return JsonResponse({'response': 'Exception'})

def post_sonarr_payload():
    try:
        time.sleep(random.uniform(0.0, 3600.0))
        mdblistarr = MDBListarr()
        series = mdblistarr.sonarr.get_series()

        provider = 2 # Sonarr JSON POST

        json = []
        for show in series:
            exists = None
            if show.get('tvdbId'):
                if show.get('seasons'):
                    exists = False
                    for season in show['seasons']:
                        if season['statistics']['percentOfEpisodes'] == 100:
                            # At least one season is downloaded 100%
                            exists = True
                elif show['monitored']:
                    exists = False
                if exists is not None:
                    json.append({'exists':exists, 'tvdb':show.get('tvdbId')})
        total_records = len(json)
        json_payload = {'sonarr': json}

        res = mdblistarr.mdblist.post_arr_payload(json_payload)
        if res['response'] == 'Ok':
            save_log(provider, OK, f'Uploaded {total_records} records to MDBList.com')
            return JsonResponse(res)
        else:
            save_log(provider, WARNING, f'Upload records to MDBList.com Failed: {res}')
            return JsonResponse(res)
    except:
        save_log(provider, ERROR, f'{traceback.format_exc()}')
        return JsonResponse({'response': 'Exception'})

def get_radarr_root_folder_from_genre(genres):
    genres_list = ast.literal_eval(genres)
    if genres_list is not None:
        dest = RadarrDestinations.objects.filter(genre__in=genres_list).first()
        if dest is None:
            dest = RadarrDestinations.objects.filter(genre='all').first()
        if dest is not None:
            root_folder = dest.root_folder
        else:
            root_folder = None
        return root_folder
    else:
        return None

def get_mdblist_queue_to_arr():
    try:
        time.sleep(random.uniform(0.0, 36.0))
        mdblistarr = MDBListarr()
        queue = mdblistarr.mdblist.get_mdblist_queue()

        for item in queue:
            if item['mediatype'] == 'movie':
                provider = 1 # RADARR
                radarr_root_folder = get_radarr_root_folder_from_genre(item.get('genres'))
                if radarr_root_folder is not None:
                    movie_request_json = {
                        "title": item['title'],
                        "tmdbId": item['tmdbid'],
                        "monitored": True, 
                        "addOptions": {"searchForMovie": True},
                        "qualityProfileId": mdblistarr.radarr_quality_profile,
                        "rootFolderPath": radarr_root_folder
                    }
                    res = mdblistarr.radarr.post_movie(movie_request_json)
                    if isinstance(res, list):
                        if res[0].get('errorMessage'):
                            save_log(provider, WARNING, f"Error adding movie to Radarr: {item['title']}. {res[0]['errorMessage']}.")
                        else:
                            save_log(provider, ERROR, f"Error posting movie to Radarr")
                    elif res.get('title'):
                        save_log(provider, OK, f"Added movie to Radarr: {item['title']}.")
                    else:
                        save_log(provider, ERROR, f"Error posting movie to Radarr")
                else:
                    save_log(provider, ERROR, f"Root folder is not set for genre {item.get('genre')}")
            elif item['mediatype'] == 'show':
                provider = 2 # SONARR
                show_request_json = {
                    "title": item['title'],
                    "tvdbId": item['tvdbid'],
                    "monitored": True, 
                    "addOptions": {"searchForMissingEpisodes": True},
                    "qualityProfileId": mdblistarr.sonarr_quality_profile,
                    "rootFolderPath": mdblistarr.sonarr_root_folder
                }
                res = mdblistarr.sonarr.post_show(show_request_json)
                if isinstance(res, list):
                    if res[0].get('errorMessage'):
                        save_log(provider, WARNING, f"Error adding show to Sonarr: {item['title']}. {res[0]['errorMessage']}")
                    else:
                        save_log(provider, ERROR, f"Error posting show to Sonarr")
                elif res.get('title'):
                    save_log(provider, OK, f"Added show to Sonarr {item['title']}.")
                else:
                    save_log(provider, ERROR, f"Error posting show to Sonarr")
    except:
        save_log(provider, ERROR, f'{traceback.format_exc()}')
        return JsonResponse({'result': 500})
    
    return JsonResponse({'result': 200})
