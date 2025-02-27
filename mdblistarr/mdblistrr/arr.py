import logging, time, json, re, traceback
from urllib.parse import urlsplit
from .connect import Connect
import traceback

class SonarrAPI():
    def __init__(self, url, apikey):
        self.connect = Connect()
        self.url = self._get_url(url)
        self.apikey = apikey

    def _get_url(self, url):
        if not re.match(r'http(s?)\:', url):
            url = 'http://' + url
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def get_status(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/system/status", params={"apikey": self.apikey})
            return {'status': 1, 'message': 'Ok', 'json': json}
        except:
            return {'status': 0, 'message': 'Error connecting to Radarr API'}

    def get_quality_profile(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/qualityprofile", params={"apikey": self.apikey})
            return json
        except:
            return [{'id': 0, 'name': 'Error connecting to Sonarr API'}]

    def get_root_folder(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/rootfolder", params={"apikey": self.apikey})
            return json
        except:
            return [{'id': 0, 'path': 'Error connecting to Sonarr API'}]

    def get_series(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/series", params={"apikey": self.apikey})
            return json
        except:
            return [{'result': 'Error connecting to Sonarr API'}]

    def post_show(self, payload):
        try:
            return(self.connect.post_json(f"{self.url}/api/v3/series", json=payload, params={"apikey": self.apikey}))
        except:
            return {'response': f'{traceback.format_exc()}'}

class RadarrAPI():
    def __init__(self, url, apikey):
        self.connect = Connect()
        self.url = self._get_url(url)
        self.apikey = apikey

    def _get_url(self, url):
        if not re.match(r'http(s?)\:', url):
            url = 'http://' + url
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def get_status(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/system/status", params={"apikey": self.apikey})
            return {'status': 1, 'message': 'Ok', 'json': json}
        except:
            return {'status': 0, 'message': 'Error connecting to Radarr API'}

    def get_quality_profile(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/qualityprofile", params={"apikey": self.apikey})
            return json
        except:
            return [{'id': 0, 'name': 'Error connecting to Radarr API'}]

    def get_root_folder(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/rootfolder", params={"apikey": self.apikey})
            return json
        except:
            return [{'id': 0, 'path': 'Error connecting to Radarr API'}]

    def get_movies(self):
        try:
            json = self.connect.get_json(f"{self.url}/api/v3/movie", params={"apikey": self.apikey})
            return json
        except:
            return [{'result': 'Error connecting to Radarr API'}]

    def post_movie(self, payload):
        try:
            return(self.connect.post_json(f"{self.url}/api/v3/movie", json=payload, params={"apikey": self.apikey}))
        except:
            return {'response': f'{traceback.format_exc()}'}

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