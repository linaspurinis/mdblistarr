import logging, time, json, re, traceback
import requests as _requests
from urllib.parse import urlsplit
from .connect import Connect, DEFAULT_HEADERS
from .models import RadarrInstance, SonarrInstance

MDBLIST_TOKEN_URL = "https://api.mdblist.com/oauth/token/"
MDBLIST_DEFAULT_CLIENT_ID = "EUk8hb6sCGab70Z08k9EKMv1kahOh311Xxk4fDrj"

class SonarrAPI():
    def __init__(self, url=None, apikey=None, instance_id=None):
        self.connect = Connect()
        self.name = None
        
        # If instance_id is provided, fetch the instance details
        if instance_id is not None:
            try:
                instance = SonarrInstance.objects.get(id=instance_id)
                self.url = self._get_url(instance.url)
                self.apikey = instance.apikey
                self.name = instance.name
            except SonarrInstance.DoesNotExist:
                raise ValueError(f"Sonarr instance with ID {instance_id} not found")
        # Otherwise use the provided URL and API key
        elif url and apikey:
            self.url = self._get_url(url)
            self.apikey = apikey
        else:
            # Fallback to default instance if no parameters provided
            try:
                instance = SonarrInstance.objects.first()
                if instance:
                    self.url = self._get_url(instance.url)
                    self.apikey = instance.apikey
                    self.name = instance.name
                else:
                    raise ValueError("No Sonarr instance found and no URL/API key provided")
            except Exception as e:
                raise ValueError(f"Failed to initialize SonarrAPI: {str(e)}")
    
    def _get_url(self, url):
        if not re.match(r'http(s?)\:', url):
            url = 'http://' + url
        parsed = urlsplit(url)
        path = parsed.path.rstrip('/')
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    
    def get_status(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/system/status", params={"apikey": self.apikey})
            return {'status': 1, 'message': 'Ok', 'json': json}
        except Exception as e:
            return {'status': 0, 'message': f'Error connecting to Sonarr API: {str(e)}'}
    
    def get_quality_profile(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/qualityprofile", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'id': 0, 'name': f'Error connecting to Sonarr API: {str(e)}'}]
    
    def get_root_folder(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/rootfolder", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'id': 0, 'path': f'Error connecting to Sonarr API: {str(e)}'}]
    
    def get_series(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/series", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'result': f'Error connecting to Sonarr API: {str(e)}'}]

    def get_episodes(self, series_id):
        """Fetch all episodes for a given series."""
        try:
            return self.connect.get_json(f"{self.url}/api/v3/episode", params={"apikey": self.apikey, "seriesId": series_id})
        except Exception as e:
            return [{'result': f'Error connecting to Sonarr API (episode): {str(e)}'}]

    def get_episode_files(self, series_id):
        """Fetch all episode files for a given series."""
        try:
            return self.connect.get_json(f"{self.url}/api/v3/episodefile", params={"apikey": self.apikey, "seriesId": series_id})
        except Exception as e:
            return [{'result': f'Error connecting to Sonarr API (episodefile): {str(e)}'}]

    def get_import_list_exclusions(self):
        """
        Import List Exclusions (Settings -> Import Lists -> List Exclusions).
        Used to mark items as excluded in the full library sync payload.
        """
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/importlistexclusion", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'result': f'Error connecting to Sonarr API (importlistexclusion): {str(e)}'}]
    
    def post_show(self, payload):
        try:
            return self.connect.post_json(f"{self.url}/api/v3/series", json=payload, params={"apikey": self.apikey})
        except Exception:
            return {'errorMessage': traceback.format_exc()}

    def get_tags(self):
        try:
            return self.connect.get_json(f"{self.url}/api/v3/tag", params={"apikey": self.apikey})
        except Exception as e:
            return [{'result': f'Error connecting to Sonarr API (tag): {str(e)}'}]

class RadarrAPI():
    def __init__(self, url=None, apikey=None, instance_id=None):
        self.connect = Connect()
        self.name = None
        
        # If instance_id is provided, fetch the instance details
        if instance_id is not None:
            try:
                instance = RadarrInstance.objects.get(id=instance_id)
                self.url = self._get_url(instance.url)
                self.apikey = instance.apikey
                self.name = instance.name
            except RadarrInstance.DoesNotExist:
                raise ValueError(f"Radarr instance with ID {instance_id} not found")
        # Otherwise use the provided URL and API key
        elif url and apikey:
            self.url = self._get_url(url)
            self.apikey = apikey
        else:
            # Fallback to default instance if no parameters provided
            try:
                instance = RadarrInstance.objects.first()
                if instance:
                    self.url = self._get_url(instance.url)
                    self.apikey = instance.apikey
                    self.name = instance.name
                else:
                    raise ValueError("No Radarr instance found and no URL/API key provided")
            except Exception as e:
                raise ValueError(f"Failed to initialize RadarrAPI: {str(e)}")
    
    def _get_url(self, url):
        if not re.match(r'http(s?)\:', url):
            url = 'http://' + url
        parsed = urlsplit(url)
        path = parsed.path.rstrip('/')
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    
    def get_status(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/system/status", params={"apikey": self.apikey})
            return {'status': 1, 'message': 'Ok', 'json': json}
        except Exception as e:
            return {'status': 0, 'message': f'Error connecting to Radarr API: {str(e)}'}
    
    def get_quality_profile(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/qualityprofile", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'id': 0, 'name': f'Error connecting to Radarr API: {str(e)}'}]
    
    def get_root_folder(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/rootfolder", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'id': 0, 'path': f'Error connecting to Radarr API: {str(e)}'}]
    
    def get_movies(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/movie", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'result': f'Error connecting to Radarr API: {str(e)}'}]

    def get_exclusions(self):
        """
        Import List Exclusions (Settings -> Import Lists -> List Exclusions).
        Used to mark items as excluded in the full library sync payload.
        """
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/exclusions", params={"apikey": self.apikey})
            return json
        except Exception as e:
            return [{'result': f'Error connecting to Radarr API (exclusions): {str(e)}'}]

    def post_movie(self, payload):
        try:
            return self.connect.post_json(f"{self.url}/api/v3/movie", json=payload, params={"apikey": self.apikey})
        except Exception:
            return {'errorMessage': traceback.format_exc()}

    def _find_movie_id_by_tmdb(self, tmdb_id):
        """
        Resolve an existing Radarr movie ID by TMDB ID.
        We try a filtered request first, then fall back to fetching all movies.
        """
        def tmdb_ids_match(left, right):
            if left is None or right is None:
                return False
            try:
                return int(left) == int(right)
            except (TypeError, ValueError):
                return str(left).strip() == str(right).strip()

        try:
            # Some Radarr versions support filtering by tmdbId.
            filtered = self.connect.get_json(
                f"{self.url}/api/v3/movie",
                params={"apikey": self.apikey, "tmdbId": tmdb_id},
            )
            if isinstance(filtered, list):
                for m in filtered:
                    if isinstance(m, dict) and tmdb_ids_match(m.get("tmdbId"), tmdb_id) and m.get("id") is not None:
                        return m["id"]
            elif isinstance(filtered, dict) and filtered.get("id") is not None and tmdb_ids_match(filtered.get("tmdbId"), tmdb_id):
                return filtered["id"]
        except Exception:
            pass

        movies = self.get_movies()
        if isinstance(movies, list):
            for m in movies:
                if isinstance(m, dict) and tmdb_ids_match(m.get("tmdbId"), tmdb_id) and m.get("id") is not None:
                    return m["id"]
        return None

    def trigger_movie_search(self, tmdb_id):
        """
        Trigger an immediate search in Radarr for a movie by TMDB ID.
        Returns the command response, or a dict with error details.
        """
        movie_id = self._find_movie_id_by_tmdb(tmdb_id)
        if movie_id is None:
            return {"error": "movie_not_found", "tmdbId": tmdb_id}

        # Radarr command: MoviesSearch expects movieIds array.
        return self.connect.post_json(
            f"{self.url}/api/v3/command",
            json={"name": "MoviesSearch", "movieIds": [movie_id]},
            params={"apikey": self.apikey},
        )

    def get_tags(self):
        try:
            return self.connect.get_json(f"{self.url}/api/v3/tag", params={"apikey": self.apikey})
        except Exception as e:
            return [{'result': f'Error connecting to Radarr API (tag): {str(e)}'}]

class MdblistAPI():
    def __init__(self, apikey=None, access_token=None, refresh_token=None, token_expires_at=None, client_id=None):
        self.connect = Connect()
        self.url = "https://mdblist.com"
        self.apikey = apikey
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires_at = token_expires_at  # float unix timestamp
        self.client_id = client_id

    @property
    def is_oauth(self):
        return bool(self.access_token)

    def _auth(self):
        if self.access_token:
            return {
                'headers': {**DEFAULT_HEADERS, 'Authorization': f'Bearer {self.access_token}'},
                'params': None,
            }
        return {'headers': None, 'params': {'apikey': self.apikey}}

    def _ensure_valid_token(self):
        if not self.access_token or not self.token_expires_at:
            return
        if time.time() > self.token_expires_at - 300:
            self._refresh_token()

    def _refresh_token(self):
        try:
            r = _requests.post(MDBLIST_TOKEN_URL, data={
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.client_id or MDBLIST_DEFAULT_CLIENT_ID,
            })
            data = r.json()
            if data.get('access_token'):
                self.access_token = data['access_token']
                self.refresh_token = data.get('refresh_token', self.refresh_token)
                self.token_expires_at = time.time() + data.get('expires_in', 2592000)
                from .models import Preferences
                Preferences.objects.update_or_create(name='mdblist_access_token', defaults={'value': self.access_token})
                Preferences.objects.update_or_create(name='mdblist_refresh_token', defaults={'value': self.refresh_token or ''})
                Preferences.objects.update_or_create(name='mdblist_token_expires_at', defaults={'value': str(int(self.token_expires_at))})
        except Exception:
            pass

    def test_api(self, apikey=None):
        try:
            if self.access_token:
                data = self.connect.get_json(
                    "https://api.mdblist.com/user",
                    headers={**DEFAULT_HEADERS, 'Authorization': f'Bearer {self.access_token}'},
                )
                return bool(data.get('user_id'))
            key = apikey if apikey else self.apikey
            data = self.connect.get_json("https://api.mdblist.com/user", params={"apikey": key})
            return bool(data.get('user_id'))
        except:
            return False

    def post_arr_payload(self, payload):
        try:
            self._ensure_valid_token()
            return self.connect.post_json("https://api.mdblist.com/arr/upload", json=payload, **self._auth())
        except:
            return {'response': f'{traceback.format_exc()}'}

    def get_mdblist_queue(self):
        try:
            self._ensure_valid_token()
            return self.connect.get_json("https://api.mdblist.com/arr/queue", **self._auth())
        except:
            return {'response': f'{traceback.format_exc()}'}

    def post_collection(self, payload):
        try:
            self._ensure_valid_token()
            return self.connect.post_json("https://api.mdblist.com/sync/collection", json=payload, **self._auth())
        except:
            return {'error': f'{traceback.format_exc()}'}

    def post_collection_remove(self, payload):
        try:
            self._ensure_valid_token()
            return self.connect.post_json("https://api.mdblist.com/sync/collection/remove", json=payload, **self._auth())
        except:
            return {'error': f'{traceback.format_exc()}'}

    def post_arr_changes(self, payload):
        try:
            self._ensure_valid_token()
            return self.connect.post_json("https://api.mdblist.com/arr/config", json=payload, **self._auth())
        except:
            return {'response': 'Exception', 'error': f'{traceback.format_exc()}'}
