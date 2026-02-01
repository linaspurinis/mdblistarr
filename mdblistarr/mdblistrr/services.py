import logging
from functools import lru_cache

from .models import Preferences, RadarrInstance, SonarrInstance
from .arr import SonarrAPI, RadarrAPI, MdblistAPI

logger = logging.getLogger(__name__)


class MDBListarr:
    def __init__(self):
        self.mdblist_apikey = None
        self.mdblist = None
        self._get_config()

        if self.mdblist_apikey:
            self.mdblist = MdblistAPI(self.mdblist_apikey)

    def _get_config(self):
        pref = Preferences.objects.filter(name="mdblist_apikey").first()
        if pref is not None:
            self.mdblist_apikey = pref.value

    def get_radarr_quality_profile_choices(self, url, apikey):
        choices_list = [("0", "Select Quality Profile")]
        try:
            radarr = RadarrAPI(url, apikey)
            if radarr:
                quality_profiles = radarr.get_quality_profile()
                for profile in quality_profiles:
                    choices_list.append((str(profile["id"]), profile["name"]))
        except Exception as e:
            logger.error(f"Error fetching Radarr quality profiles: {str(e)}")
        return choices_list

    def get_radarr_root_folder_choices(self, url, apikey):
        choices_list = [("0", "Select Root Folder")]
        try:
            radarr = RadarrAPI(url, apikey)
            if radarr:
                root_folders = radarr.get_root_folder()
                for folder in root_folders:
                    choices_list.append((folder["path"], folder["path"]))
        except Exception as e:
            logger.error(f"Error fetching Radarr root folders: {str(e)}")
        return choices_list

    def get_sonarr_quality_profile_choices(self, url, apikey):
        choices_list = [("0", "Select Quality Profile")]
        try:
            sonarr = SonarrAPI(url, apikey)
            if sonarr:
                quality_profiles = sonarr.get_quality_profile()
                for profile in quality_profiles:
                    choices_list.append((str(profile["id"]), profile["name"]))
        except Exception as e:
            logger.error(f"Error fetching Sonarr quality profiles: {str(e)}")
        return choices_list

    def get_sonarr_root_folder_choices(self, url, apikey):
        choices_list = [("0", "Select Root Folder")]
        try:
            sonarr = SonarrAPI(url, apikey)
            if sonarr:
                root_folders = sonarr.get_root_folder()
                for folder in root_folders:
                    choices_list.append((folder["path"], folder["path"]))
        except Exception as e:
            logger.error(f"Error fetching Sonarr root folders: {str(e)}")
        return choices_list

    def test_radarr_connection(self, url, apikey):
        try:
            radarr = RadarrAPI(url, apikey)
            status = radarr.get_status()
            if status["status"] == 1:
                return {
                    "status": True,
                    "version": f"{status['json']['instanceName']} {status['json']['version']}",
                }
        except Exception:
            pass
        return {"status": False, "version": ""}

    def test_sonarr_connection(self, url, apikey):
        try:
            sonarr = SonarrAPI(url, apikey)
            status = sonarr.get_status()
            if status["status"] == 1:
                return {
                    "status": True,
                    "version": f"{status['json']['instanceName']} {status['json']['version']}",
                }
        except Exception:
            pass
        return {"status": False, "version": ""}

    def get_radarr_quality_profile(self, instance_id=None):
        """
        Get quality profile ID for a Radarr instance.
        Returns the quality profile ID of the specified instance or the first available instance if not found.
        """
        try:
            if instance_id:
                instance = RadarrInstance.objects.filter(id=instance_id).first()
                if instance and instance.quality_profile:
                    return instance.quality_profile

            first_instance = RadarrInstance.objects.filter(
                quality_profile__isnull=False
            ).first()
            if first_instance:
                return first_instance.quality_profile

            return 0
        except Exception as e:
            logger.error(f"Error getting Radarr quality profile: {str(e)}")
            return 0

    def get_radarr_root_folder(self, instance_id=None):
        """
        Get root folder path for a Radarr instance.
        Returns the root folder path of the specified instance or the first available instance if not found.
        """
        try:
            if instance_id:
                instance = RadarrInstance.objects.filter(id=instance_id).first()
                if instance and instance.root_folder:
                    return instance.root_folder

            first_instance = RadarrInstance.objects.filter(
                root_folder__isnull=False
            ).first()
            if first_instance:
                return first_instance.root_folder

            return ""
        except Exception as e:
            logger.error(f"Error getting Radarr root folder: {str(e)}")
            return ""

    def get_sonarr_quality_profile(self, instance_id=None):
        """
        Get quality profile ID for a Radarr instance.
        Returns the quality profile ID of the specified instance or the first available instance if not found.
        """
        try:
            if instance_id:
                instance = SonarrInstance.objects.filter(id=instance_id).first()
                if instance and instance.quality_profile:
                    return instance.quality_profile

            first_instance = SonarrInstance.objects.filter(
                quality_profile__isnull=False
            ).first()
            if first_instance:
                return first_instance.quality_profile

            return 0
        except Exception as e:
            logger.error(f"Error getting Radarr quality profile: {str(e)}")
            return 0

    def get_sonarr_root_folder(self, instance_id=None):
        """
        Get root folder path for a Radarr instance.
        Returns the root folder path of the specified instance or the first available instance if not found.
        """
        try:
            if instance_id:
                instance = SonarrInstance.objects.filter(id=instance_id).first()
                if instance and instance.root_folder:
                    return instance.root_folder

            first_instance = SonarrInstance.objects.filter(
                root_folder__isnull=False
            ).first()
            if first_instance:
                return first_instance.root_folder

            return ""
        except Exception as e:
            logger.error(f"Error getting Radarr root folder: {str(e)}")
            return ""


@lru_cache(maxsize=1)
def get_mdblistarr():
    return MDBListarr()


def reset_mdblistarr():
    get_mdblistarr.cache_clear()
