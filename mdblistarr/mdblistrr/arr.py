import logging, time, json, re, traceback
from urllib.parse import urlsplit
from .connect import Connect
import traceback
from .models import RadarrInstance, SonarrInstance

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
        return f"{parsed.scheme}://{parsed.netloc}"
    
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
    
    def post_show(self, payload):
        try:
            return self.connect.post_json(f"{self.url}/api/v3/series", json=payload, params={"apikey": self.apikey})
        except Exception as e:
            return {'response': f'Error: {traceback.format_exc()}'}

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
        return f"{parsed.scheme}://{parsed.netloc}"
    
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
    
    def post_movie(self, payload):
        try:
            return self.connect.post_json(f"{self.url}/api/v3/movie", json=payload, params={"apikey": self.apikey})
        except Exception as e:
            return {'response': f'Error: {traceback.format_exc()}'}

class MdblistAPI():
    def __init__(self, apikey):
        self.connect = Connect()
        self.url = "https://mdblist.com"
        self.apikey = apikey

    def test_api(self, apikey):
        try:
            json = self.connect.get_json(f"{self.url}/api", params={"apikey": apikey if apikey else self.apikey, 'i': 'tt0073195'})
            if json.get('title'):
                return True
            else:
                return False
        except:
            return False

    def post_arr_payload(self, payload):
        try:
            return(self.connect.post_json(f"{self.url}/service/mdblist/arr", json=payload, params={"apikey": self.apikey}))
        except:
            return {'response': f'{traceback.format_exc()}'}

    def get_mdblist_queue(self):
        try:
            return(self.connect.get_json(f"{self.url}/service/mdblist/queue", params={"apikey": self.apikey}))
        except:
            return {'response': f'{traceback.format_exc()}'}

    def post_arr_changes(self, payload):
        try:
            return(self.connect.post_json(f"{self.url}/service/mdblist/config", json=payload, params={"apikey": self.apikey}))
        except:
            return {'response': 'Exception', 'error': f'{traceback.format_exc()}'}