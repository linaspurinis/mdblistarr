from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseRedirect
from django import forms
from django.urls import reverse
from .models import Preferences, RadarrInstance, SonarrInstance
from .connect import Connect
from .arr import SonarrAPI
from .arr import RadarrAPI
from .arr import MdblistAPI
import traceback
import json
import logging
from django.contrib import messages
# Set up logging
logger = logging.getLogger(__name__)

class MDBListarr():
    def __init__(self):
        self.mdblist_apikey = None
        self.mdblist = None
        self._get_config()

        if self.mdblist_apikey:
            self.mdblist = MdblistAPI(self.mdblist_apikey)

    def _get_config(self):
        pref = Preferences.objects.filter(name='mdblist_apikey').first()
        if pref is not None: 
            self.mdblist_apikey = pref.value

    def get_radarr_quality_profile_choices(self, url, apikey):
        choices_list = [('0', 'Select Quality Profile')]
        try:
            radarr = RadarrAPI(url, apikey)
            if radarr:
                quality_profiles = radarr.get_quality_profile()
                for profile in quality_profiles:
                    choices_list.append((str(profile['id']), profile['name']))
        except Exception as e:
            logger.error(f"Error fetching Radarr quality profiles: {str(e)}")
        return choices_list

    def get_radarr_root_folder_choices(self, url, apikey):
        choices_list = [('0', 'Select Root Folder')]
        try:
            radarr = RadarrAPI(url, apikey)
            if radarr:
                root_folders = radarr.get_root_folder()
                for folder in root_folders:
                    choices_list.append((folder['path'], folder['path']))
        except Exception as e:
            logger.error(f"Error fetching Radarr root folders: {str(e)}")
        return choices_list

    def get_sonarr_quality_profile_choices(self, url, apikey):
        choices_list = [('0', 'Select Quality Profile')]
        try:
            sonarr = SonarrAPI(url, apikey)
            if sonarr:
                quality_profiles = sonarr.get_quality_profile()
                for profile in quality_profiles:
                    choices_list.append((str(profile['id']), profile['name']))
        except Exception as e:
            logger.error(f"Error fetching Sonarr quality profiles: {str(e)}")
        return choices_list

    def get_sonarr_root_folder_choices(self, url, apikey):
        choices_list = [('0', 'Select Root Folder')]
        try:
            sonarr = SonarrAPI(url, apikey)
            if sonarr:
                root_folders = sonarr.get_root_folder()
                for folder in root_folders:
                    choices_list.append((folder['path'], folder['path']))
        except Exception as e:
            logger.error(f"Error fetching Sonarr root folders: {str(e)}")
        return choices_list

    def test_radarr_connection(self, url, apikey):
        try:
            radarr = RadarrAPI(url, apikey)
            status = radarr.get_status()
            if status['status'] == 1:
                return {
                    'status': True, 
                    'version': f"{status['json']['instanceName']} {status['json']['version']}"
                }
        except Exception:
            pass
        return {'status': False, 'version': ''}

    def test_sonarr_connection(self, url, apikey):
        try:
            sonarr = SonarrAPI(url, apikey)
            status = sonarr.get_status()
            if status['status'] == 1:
                return {
                    'status': True, 
                    'version': f"{status['json']['instanceName']} {status['json']['version']}"
                }
        except Exception:
            pass
        return {'status': False, 'version': ''}


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
            
            first_instance = RadarrInstance.objects.filter(quality_profile__isnull=False).first()
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
            
            first_instance = RadarrInstance.objects.filter(root_folder__isnull=False).first()
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
            
            first_instance = SonarrInstance.objects.filter(quality_profile__isnull=False).first()
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
            
            first_instance = SonarrInstance.objects.filter(root_folder__isnull=False).first()
            if first_instance:
                return first_instance.root_folder
            
            return "" 
        except Exception as e:
            logger.error(f"Error getting Radarr root folder: {str(e)}")
            return ""  


mdblistarr = MDBListarr()

class MDBListForm(forms.Form):
    mdblist_apikey = forms.CharField(
        label='MDBList API Key', 
        widget=forms.TextInput(attrs={'placeholder': 'Enter your mdblist.com API key', 'class': 'form-control'})
    )

    def clean(self):
        cleaned_data = super().clean()
        mdblist_apikey = cleaned_data.get('mdblist_apikey')
        
        if mdblist_apikey:
            if mdblistarr.mdblist is None:
                mdblistarr.mdblist = MdblistAPI(mdblist_apikey)
            if not mdblistarr.mdblist.test_api(mdblist_apikey):
                self._errors['mdblist_apikey'] = self.error_class(['API key is invalid, unable to connect'])
                self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
                # self.add_error(None, "API key is invalid. Unable to save changes.")

            else:
                self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-valid'})
        
        return cleaned_data

class ServerSelectionForm(forms.Form):
    server_selection = forms.ChoiceField(
        label='Select Server',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, choices=None, **kwargs):
        super(ServerSelectionForm, self).__init__(*args, **kwargs)
        if choices:
            self.fields['server_selection'].choices = choices

class RadarrInstanceForm(forms.ModelForm):
    class Meta:
        model = RadarrInstance
        fields = ['name', 'url', 'apikey', 'quality_profile', 'root_folder']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Instance Name', 'class': 'form-control'}),
            'url': forms.TextInput(attrs={'placeholder': 'Radarr URL', 'class': 'form-control'}),
            'apikey': forms.TextInput(attrs={'placeholder': 'Radarr API Key', 'class': 'form-control'}),
            'quality_profile': forms.Select(attrs={'class': 'form-control'}),
            'root_folder': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super(RadarrInstanceForm, self).__init__(*args, **kwargs)
        
        self.fields['quality_profile'].choices = [('0', 'Select Quality Profile')]
        self.fields['root_folder'].choices = [('0', 'Select Root Folder')]
        
        if self.instance and self.instance.pk and self.instance.url and self.instance.apikey:
            try:
                quality_choices = mdblistarr.get_radarr_quality_profile_choices(self.instance.url, self.instance.apikey)
                root_choices = mdblistarr.get_radarr_root_folder_choices(self.instance.url, self.instance.apikey)
                
                self.fields['quality_profile'].choices = quality_choices
                self.fields['root_folder'].choices = root_choices
                
                if self.instance.quality_profile and not any(str(self.instance.quality_profile) == choice[0] for choice in quality_choices):
                    self.fields['quality_profile'].choices.append((self.instance.quality_profile, f"Profile {self.instance.quality_profile} (saved)"))
                
                if self.instance.root_folder and not any(self.instance.root_folder == choice[0] for choice in root_choices):
                    self.fields['root_folder'].choices.append((self.instance.root_folder, self.instance.root_folder))
            except Exception as e:
                logger.error(f"Error initializing RadarrInstanceForm: {str(e)}")

class SonarrInstanceForm(forms.ModelForm):
    class Meta:
        model = SonarrInstance
        fields = ['name', 'url', 'apikey', 'quality_profile', 'root_folder']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Instance Name', 'class': 'form-control'}),
            'url': forms.TextInput(attrs={'placeholder': 'Sonarr URL', 'class': 'form-control'}),
            'apikey': forms.TextInput(attrs={'placeholder': 'Sonarr API Key', 'class': 'form-control'}),
            'quality_profile': forms.Select(attrs={'class': 'form-control'}),
            'root_folder': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super(SonarrInstanceForm, self).__init__(*args, **kwargs)
        
        self.fields['quality_profile'].choices = [('0', 'Select Quality Profile')]
        self.fields['root_folder'].choices = [('0', 'Select Root Folder')]
        
        if self.instance and self.instance.pk and self.instance.url and self.instance.apikey:
            try:
                quality_choices = mdblistarr.get_sonarr_quality_profile_choices(self.instance.url, self.instance.apikey)
                root_choices = mdblistarr.get_sonarr_root_folder_choices(self.instance.url, self.instance.apikey)
                
                self.fields['quality_profile'].choices = quality_choices
                self.fields['root_folder'].choices = root_choices
                
                if self.instance.quality_profile and not any(str(self.instance.quality_profile) == choice[0] for choice in quality_choices):
                    self.fields['quality_profile'].choices.append((self.instance.quality_profile, f"Profile {self.instance.quality_profile} (saved)"))
                
                if self.instance.root_folder and not any(self.instance.root_folder == choice[0] for choice in root_choices):
                    self.fields['root_folder'].choices.append((self.instance.root_folder, self.instance.root_folder))
            except Exception as e:
                logger.error(f"Error initializing SonarrInstanceForm: {str(e)}")

def home_view(request):
    mdblist_form = MDBListForm(initial={'mdblist_apikey': mdblistarr.mdblist_apikey})
    
    radarr_instances = RadarrInstance.objects.all()
    sonarr_instances = SonarrInstance.objects.all()
    
    radarr_choices = [('new', '--- Add New Radarr Server ---')]
    radarr_choices.extend([(str(instance.id), instance.name) for instance in radarr_instances])
    
    sonarr_choices = [('new', '--- Add New Sonarr Server ---')]
    sonarr_choices.extend([(str(instance.id), instance.name) for instance in sonarr_instances])
    
    radarr_selection_form = ServerSelectionForm(choices=radarr_choices, prefix='radarr_select')
    sonarr_selection_form = ServerSelectionForm(choices=sonarr_choices, prefix='sonarr_select')
    
    radarr_form = RadarrInstanceForm()
    sonarr_form = SonarrInstanceForm()
    
    active_radarr_id = None
    active_sonarr_id = None
    
    if request.method == "POST":
        form_type = request.POST.get('form_type', '')
        
        if form_type == 'mdblist':
            mdblist_form = MDBListForm(request.POST)
            if mdblist_form.is_valid():
                Preferences.objects.update_or_create(
                    name='mdblist_apikey', 
                    defaults={'value': mdblist_form.cleaned_data['mdblist_apikey']}
                )
                mdblistarr.mdblist_apikey = mdblist_form.cleaned_data['mdblist_apikey']
                messages.success(request, "MDBList configuration saved successfully!")
                return HttpResponseRedirect(reverse('home_view'))
        
        elif form_type == 'radarr_select':
            radarr_selection_form = ServerSelectionForm(request.POST, choices=radarr_choices, prefix='radarr_select')
            if radarr_selection_form.is_valid():
                server_id = radarr_selection_form.cleaned_data['server_selection']
                if server_id != 'new':
                    active_radarr_id = server_id
                    instance = RadarrInstance.objects.get(id=server_id)
                    radarr_form = RadarrInstanceForm(instance=instance)
                else:
                    radarr_form = RadarrInstanceForm()
        
        elif form_type == 'sonarr_select':
            sonarr_selection_form = ServerSelectionForm(request.POST, choices=sonarr_choices, prefix='sonarr_select')
            if sonarr_selection_form.is_valid():
                server_id = sonarr_selection_form.cleaned_data['server_selection']
                if server_id != 'new':
                    active_sonarr_id = server_id
                    instance = SonarrInstance.objects.get(id=server_id)
                    sonarr_form = SonarrInstanceForm(instance=instance)
                else:
                    sonarr_form = SonarrInstanceForm()
        
        elif form_type == 'radarr_save':
            instance_id = request.POST.get('instance_id')
            
            if instance_id and instance_id != 'new':
                instance = get_object_or_404(RadarrInstance, id=instance_id)
                radarr_form = RadarrInstanceForm(request.POST, instance=instance)
                active_radarr_id = instance_id
            else:
                radarr_form = RadarrInstanceForm(request.POST)
            
            if radarr_form.is_valid():
                instance = radarr_form.save(commit=False)
                
                connection = mdblistarr.test_radarr_connection(instance.url, instance.apikey)
                
                if connection['status']:
                    instance.save()
                    messages.success(request, "Radarr configuration saved successfully!")
                    return HttpResponseRedirect(reverse('home_view'))
                else:
                    radarr_form.add_error('apikey', 'Unable to connect to Radarr')
                    radarr_form.fields['apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
        
        elif form_type == 'sonarr_save':
            instance_id = request.POST.get('instance_id')
            
            if instance_id and instance_id != 'new':
                instance = get_object_or_404(SonarrInstance, id=instance_id)
                sonarr_form = SonarrInstanceForm(request.POST, instance=instance)
                active_sonarr_id = instance_id
            else:
                sonarr_form = SonarrInstanceForm(request.POST)
            
            if sonarr_form.is_valid():
                instance = sonarr_form.save(commit=False)
                
                connection = mdblistarr.test_sonarr_connection(instance.url, instance.apikey)
                
                if connection['status']:
                    instance.save()
                    messages.success(request, "Sonarr configuration saved successfully!")
                    return HttpResponseRedirect(reverse('home_view'))
                else:
                    sonarr_form.add_error('apikey', 'Unable to connect to Sonarr')
                    sonarr_form.fields['apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
        
        elif form_type == 'radarr_delete':
            instance_id = request.POST.get('instance_id')
            if instance_id:
                RadarrInstance.objects.filter(id=instance_id).delete()
                return HttpResponseRedirect(reverse('home_view'))
        
        elif form_type == 'sonarr_delete':
            instance_id = request.POST.get('instance_id')
            if instance_id:
                SonarrInstance.objects.filter(id=instance_id).delete()
                return HttpResponseRedirect(reverse('home_view'))
        

    if active_radarr_id:
        radarr_selection_form.initial = {'server_selection': active_radarr_id}
    if active_sonarr_id:
        sonarr_selection_form.initial = {'server_selection': active_sonarr_id}
    
    context = {
        'mdblist_form': mdblist_form,
        'radarr_selection_form': radarr_selection_form,
        'sonarr_selection_form': sonarr_selection_form,
        'radarr_form': radarr_form,
        'sonarr_form': sonarr_form,
        'active_radarr_id': active_radarr_id,
        'active_sonarr_id': active_sonarr_id,
    }
    
    return render(request, "index.html", context)

@csrf_exempt
def test_radarr_connection(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        url = data.get('url')
        apikey = data.get('apikey')
        
        result = mdblistarr.test_radarr_connection(url, apikey)
        
        if result['status']:
            quality_profiles = mdblistarr.get_radarr_quality_profile_choices(url, apikey)
            root_folders = mdblistarr.get_radarr_root_folder_choices(url, apikey)
            
            return JsonResponse({
                'status': 'success',
                'version': result['version'],
                'quality_profiles': quality_profiles,
                'root_folders': root_folders
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Unable to connect to Radarr'
            })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@csrf_exempt
def test_sonarr_connection(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        url = data.get('url')
        apikey = data.get('apikey')
        
        result = mdblistarr.test_sonarr_connection(url, apikey)
        
        if result['status']:
            quality_profiles = mdblistarr.get_sonarr_quality_profile_choices(url, apikey)
            root_folders = mdblistarr.get_sonarr_root_folder_choices(url, apikey)
            
            return JsonResponse({
                'status': 'success',
                'version': result['version'],
                'quality_profiles': quality_profiles,
                'root_folders': root_folders
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Unable to connect to Sonarr'
            })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})