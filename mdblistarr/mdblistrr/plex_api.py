import re
import traceback
from urllib.parse import urlsplit

from .connect import Connect
from .models import PlexInstance

PLEX_CLIENT_ID = 'mdblistarr-app'
PLEX_PRODUCT = 'mdblistarr'
PLEX_VERSION = '1.0.0'
PLEX_DEVICE = 'mdblistarr'

GUID_PROVIDERS = ('imdb', 'tmdb', 'tvdb')
SECTION_TYPE_CODE = {'movie': 1, 'show': 2}  # Plex's numeric `type` param for the metadata-edit endpoint


def parse_guids(metadata_item):
    """
    Plex's `Guid` array looks like [{"id": "imdb://tt1234567"}, {"id": "tmdb://456"}, ...].
    Returns a dict with whichever of imdb/tmdb/tvdb ids are present.
    """
    guids = {}
    for guid in metadata_item.get('Guid') or []:
        guid_id = guid.get('id') if isinstance(guid, dict) else None
        if not guid_id or '://' not in guid_id:
            continue
        provider, value = guid_id.split('://', 1)
        if provider in GUID_PROVIDERS and value:
            guids[provider] = value
    return guids


class PlexServerAPI():
    def __init__(self, url=None, token=None, instance_id=None):
        self.connect = Connect()
        self.name = None

        if instance_id is not None:
            instance = PlexInstance.objects.get(id=instance_id)
            self.url = self._get_url(instance.url)
            self.token = instance.token
            self.name = instance.name
        elif url and token:
            self.url = self._get_url(url)
            self.token = token
        else:
            raise ValueError("PlexServerAPI requires either instance_id or url+token")

    def _get_url(self, url):
        if not re.match(r'http(s?):', url):
            url = 'http://' + url
        parsed = urlsplit(url)
        path = parsed.path.rstrip('/')
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    def _headers(self):
        return {'Accept': 'application/json', 'X-Plex-Token': self.token}

    def test_connection(self):
        try:
            response = self.connect.get(f"{self.url}/identity", headers=self._headers())
            if response.status_code == 200:
                data = response.json()
                version = (data.get('MediaContainer') or {}).get('version', '')
                return {'status': True, 'version': version}
        except Exception:
            pass
        return {'status': False, 'version': ''}

    def get_sections(self):
        try:
            response = self.connect.get(f"{self.url}/library/sections", headers=self._headers())
            data = response.json()
            directories = (data.get('MediaContainer') or {}).get('Directory') or []
            sections = []
            for d in directories:
                if d.get('type') not in ('movie', 'show'):
                    continue
                sections.append({'id': str(d.get('key')), 'title': d.get('title'), 'type': d.get('type')})
            return sections
        except Exception:
            return []

    def get_section_items(self, section_id):
        try:
            response = self.connect.get(
                f"{self.url}/library/sections/{section_id}/all",
                headers=self._headers(),
                params={'includeGuids': '1'},
            )
            data = response.json()
            items = (data.get('MediaContainer') or {}).get('Metadata') or []
            results = []
            for item in items:
                rating_key = item.get('ratingKey')
                if not rating_key:
                    continue
                results.append({
                    'rating_key': str(rating_key),
                    'title': item.get('title'),
                    'type': item.get('type'),
                    'thumb': item.get('thumb') or '',
                    'guids': parse_guids(item),
                    'audience_rating': item.get('audienceRating'),
                    'year': item.get('year'),
                })
            return results
        except Exception:
            return []

    def get_item_thumb(self, rating_key):
        """Cheap metadata refresh (no image download) to read the current `thumb` revision key."""
        try:
            response = self.connect.get(
                f"{self.url}/library/metadata/{rating_key}",
                headers=self._headers(),
            )
            data = response.json()
            items = (data.get('MediaContainer') or {}).get('Metadata') or []
            if items:
                return items[0].get('thumb') or ''
        except Exception:
            pass
        return None

    def get_poster_bytes(self, thumb_path):
        try:
            response = self.connect.get(
                f"{self.url}{thumb_path}",
                headers={'X-Plex-Token': self.token},
            )
            if response.status_code == 200 and response.content:
                return response.content
        except Exception:
            pass
        return None

    def upload_poster(self, rating_key, image_bytes):
        try:
            response = self.connect.post(
                f"{self.url}/library/metadata/{rating_key}/posters",
                data=image_bytes,
                headers={'X-Plex-Token': self.token, 'Content-Type': 'image/jpeg'},
            )
            return response.status_code in (200, 201)
        except Exception:
            return False

    def set_audience_rating(self, section_id, media_type, rating_key, value, locked=True):
        """
        Overwrite + lock (or unlock) the audienceRating field via Plex's bulk
        metadata-edit endpoint, scoped to a single item via id=. Locking stops
        Plex's agent from reverting it on the next scheduled metadata refresh
        (same mechanism python-plexapi/Kometa use).
        """
        type_code = SECTION_TYPE_CODE.get(media_type)
        if type_code is None:
            return False
        try:
            response = self.connect.put(
                f"{self.url}/library/sections/{section_id}/all",
                headers=self._headers(),
                params={
                    'type': type_code,
                    'id': rating_key,
                    'audienceRating.value': value,
                    'audienceRating.locked': 1 if locked else 0,
                },
            )
            return response.status_code in (200, 201)
        except Exception:
            return False
