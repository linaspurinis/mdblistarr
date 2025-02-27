from django.shortcuts import render, redirect
from django.views.generic import ListView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseRedirect
from django import forms
from django.urls import reverse
from .models import Preferences, RadarrInstance, SonarrInstance
from .connect import Connect
from .arr import SonarrAPI
from .arr import RadarrAPI
from .arr import MdblistAPI
from django.core.exceptions import ValidationError
import traceback
import json

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
                    choices_list.append((profile['id'], profile['name']))
        except Exception:
            pass
        return choices_list

    def get_radarr_root_folder_choices(self, url, apikey):
        choices_list = [('0', 'Select Root Folder')]
        try:
            radarr = RadarrAPI(url, apikey)
            if radarr:
                root_folders = radarr.get_root_folder()
                for folder in root_folders:
                    choices_list.append((folder['path'], folder['path']))
        except Exception:
            pass
        return choices_list

    def get_sonarr_quality_profile_choices(self, url, apikey):
        choices_list = [('0', 'Select Quality Profile')]
        try:
            sonarr = SonarrAPI(url, apikey)
            if sonarr:
                quality_profiles = sonarr.get_quality_profile()
                for profile in quality_profiles:
                    choices_list.append((profile['id'], profile['name']))
        except Exception:
            pass
        return choices_list

    def get_sonarr_root_folder_choices(self, url, apikey):
        choices_list = [('0', 'Select Root Folder')]
        try:
            sonarr = SonarrAPI(url, apikey)
            if sonarr:
                root_folders = sonarr.get_root_folder()
                for folder in root_folders:
                    choices_list.append((folder['path'], folder['path']))
        except Exception:
            pass
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

mdblistarr = MDBListarr()

class MDBListForm(forms.Form):
    mdblist_apikey = forms.CharField(
        label='MDBList API Key', 
        widget=forms.TextInput(attrs={'placeholder': 'Enter your mdblist.com API key', 'class': 'form-control'})
    )

    def clean(self):
        cleaned_data = super().clean()
        mdblist_apikey = cleaned_data.get('mdblist_apikey')
        
        if mdblistarr.mdblist is None:
            mdblistarr.mdblist = MdblistAPI(mdblist_apikey)
        if not mdblistarr.mdblist.test_api(mdblist_apikey):
            self._errors['mdblist_apikey'] = self.error_class(['API key is invalid, unable to connect'])
            self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
            self.add_error(None, "API key is invalid. Unable to save changes.")
        else:
            self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-valid'})
        
        return cleaned_data

class RadarrInstanceForm(forms.ModelForm):
    test_connection = forms.BooleanField(required=False, widget=forms.HiddenInput())
    
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
        
        # Check bound data first (for POST submissions)
        if self.is_bound and 'url' in self.data and 'apikey' in self.data:
            url = self.data.get('url')
            apikey = self.data.get('apikey')
            if url and apikey:
                self.fields['quality_profile'].choices = mdblistarr.get_radarr_quality_profile_choices(url, apikey)
                self.fields['root_folder'].choices = mdblistarr.get_radarr_root_folder_choices(url, apikey)
        # Then check instance data (for existing instances)
        elif self.instance and self.instance.url and self.instance.apikey:
            self.fields['quality_profile'].choices = mdblistarr.get_radarr_quality_profile_choices(
                self.instance.url, self.instance.apikey
            )
            self.fields['root_folder'].choices = mdblistarr.get_radarr_root_folder_choices(
                self.instance.url, self.instance.apikey
            )
    
    def clean(self):
        cleaned_data = super().clean()
        url = cleaned_data.get('url')
        apikey = cleaned_data.get('apikey')
        quality_profile = cleaned_data.get('quality_profile')
        root_folder = cleaned_data.get('root_folder')
        test_connection = cleaned_data.get('test_connection')
        
        found_error = False
        
        if url and apikey and (not self.instance.pk or test_connection):
            connection = mdblistarr.test_radarr_connection(url, apikey)
            if connection['status']:
                self.fields['apikey'].widget.attrs.update({'class': 'form-control is-valid'})
                self.fields['apikey'].help_text = connection['version']
                
                self.fields['quality_profile'].choices = mdblistarr.get_radarr_quality_profile_choices(url, apikey)
                self.fields['root_folder'].choices = mdblistarr.get_radarr_root_folder_choices(url, apikey)
                
                if quality_profile == '0' or not quality_profile:
                    self._errors['quality_profile'] = self.error_class(['Select a quality profile'])
                    self.fields['quality_profile'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True
                
                if root_folder == '0' or not root_folder:
                    self._errors['root_folder'] = self.error_class(['Select a root folder'])
                    self.fields['root_folder'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True
            else:
                self._errors['apikey'] = self.error_class(['Unable to connect to Radarr'])
                self.fields['apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
                found_error = True
        
        if found_error:
            self.add_error(None, "Please correct the errors to save changes.")
        
        return cleaned_data

class SonarrInstanceForm(forms.ModelForm):
    test_connection = forms.BooleanField(required=False, widget=forms.HiddenInput())
    
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
        
        if self.is_bound and 'url' in self.data and 'apikey' in self.data:
            url = self.data.get('url')
            apikey = self.data.get('apikey')
            if url and apikey:
                self.fields['quality_profile'].choices = mdblistarr.get_sonarr_quality_profile_choices(url, apikey)
                self.fields['root_folder'].choices = mdblistarr.get_sonarr_root_folder_choices(url, apikey)
        elif self.instance and self.instance.url and self.instance.apikey:
            self.fields['quality_profile'].choices = mdblistarr.get_sonarr_quality_profile_choices(
                self.instance.url, self.instance.apikey
            )
            self.fields['root_folder'].choices = mdblistarr.get_sonarr_root_folder_choices(
                self.instance.url, self.instance.apikey
            )
    
    def clean(self):
        cleaned_data = super().clean()
        url = cleaned_data.get('url')
        apikey = cleaned_data.get('apikey')
        quality_profile = cleaned_data.get('quality_profile')
        root_folder = cleaned_data.get('root_folder')
        test_connection = cleaned_data.get('test_connection')
        
        found_error = False
        
        if url and apikey and (not self.instance.pk or test_connection):
            connection = mdblistarr.test_sonarr_connection(url, apikey)
            if connection['status']:
                self.fields['apikey'].widget.attrs.update({'class': 'form-control is-valid'})
                self.fields['apikey'].help_text = connection['version']
                
                self.fields['quality_profile'].choices = mdblistarr.get_sonarr_quality_profile_choices(url, apikey)
                self.fields['root_folder'].choices = mdblistarr.get_sonarr_root_folder_choices(url, apikey)
                
                if quality_profile == '0' or not quality_profile:
                    self._errors['quality_profile'] = self.error_class(['Select a quality profile'])
                    self.fields['quality_profile'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True
                
                if root_folder == '0' or not root_folder:
                    self._errors['root_folder'] = self.error_class(['Select a root folder'])
                    self.fields['root_folder'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True
            else:
                self._errors['apikey'] = self.error_class(['Unable to connect to Sonarr'])
                self.fields['apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
                found_error = True
        
        if found_error:
            self.add_error(None, "Please correct the errors to save changes.")
        
        return cleaned_data

def home_view(request):
    mdblist_form = MDBListForm(initial={'mdblist_apikey': mdblistarr.mdblist_apikey})
    
    radarr_instances = RadarrInstance.objects.all()
    radarr_forms = []
    for instance in radarr_instances:
        radarr_forms.append(RadarrInstanceForm(instance=instance, prefix=f'radarr_{instance.id}'))
    if not radarr_instances or request.GET.get('add_radarr'):
        radarr_forms.append(RadarrInstanceForm(prefix='radarr_new'))
    
    sonarr_instances = SonarrInstance.objects.all()
    sonarr_forms = []
    for instance in sonarr_instances:
        sonarr_forms.append(SonarrInstanceForm(instance=instance, prefix=f'sonarr_{instance.id}'))
    if not sonarr_instances or request.GET.get('add_sonarr'):
        sonarr_forms.append(SonarrInstanceForm(prefix='sonarr_new'))
    
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
                return HttpResponseRedirect(reverse('home_view'))
        
        elif form_type.startswith('radarr_'):
            instance_id = form_type.split('_')[1]
            if instance_id == 'new':
                form = RadarrInstanceForm(request.POST, prefix='radarr_new')
                if form.is_valid():
                    form.save()
                    return HttpResponseRedirect(reverse('home_view'))
                else:
                    radarr_forms = [form if f.prefix == 'radarr_new' else f for f in radarr_forms]
            else:
                instance = RadarrInstance.objects.get(id=instance_id)
                form = RadarrInstanceForm(request.POST, instance=instance, prefix=f'radarr_{instance_id}')
                if form.is_valid():
                    form.save()
                    return HttpResponseRedirect(reverse('home_view'))
                else:
                    radarr_forms = [form if f.prefix == f'radarr_{instance_id}' else f for f in radarr_forms]
        
        elif form_type.startswith('sonarr_'):
            instance_id = form_type.split('_')[1]
            if instance_id == 'new':
                form = SonarrInstanceForm(request.POST, prefix='sonarr_new')
                if form.is_valid():
                    form.save()
                    return HttpResponseRedirect(reverse('home_view'))
                else:
                    sonarr_forms = [form if f.prefix == 'sonarr_new' else f for f in sonarr_forms]
            else:
                instance = SonarrInstance.objects.get(id=instance_id)
                form = SonarrInstanceForm(request.POST, instance=instance, prefix=f'sonarr_{instance_id}')
                if form.is_valid():
                    form.save()
                    return HttpResponseRedirect(reverse('home_view'))
                else:
                    sonarr_forms = [form if f.prefix == f'sonarr_{instance_id}' else f for f in sonarr_forms]
        
        elif form_type.startswith('delete_'):
            parts = form_type.split('_')
            model_type = parts[1]
            instance_id = parts[2]
            if model_type == 'radarr' and RadarrInstance.objects.count() > 1:
                RadarrInstance.objects.filter(id=instance_id).delete()
            elif model_type == 'sonarr' and SonarrInstance.objects.count() > 1:
                SonarrInstance.objects.filter(id=instance_id).delete()
            return HttpResponseRedirect(reverse('home_view'))
        
        elif form_type.startswith('test_'):
            parts = form_type.split('_')
            model_type = parts[1]
            instance_id = parts[2]
            
            if model_type == 'radarr':
                if instance_id == 'new':
                    form = RadarrInstanceForm(request.POST, prefix='radarr_new')
                    form.data = form.data.copy()
                    form.data['radarr_new-test_connection'] = True
                    if form.is_valid():
                        updated_form = RadarrInstanceForm(
                            initial={
                                'name': form.cleaned_data['name'],
                                'url': form.cleaned_data['url'],
                                'apikey': form.cleaned_data['apikey'],
                                'quality_profile': form.cleaned_data['quality_profile'],
                                'root_folder': form.cleaned_data['root_folder'],
                            },
                            prefix='radarr_new'
                        )
                        radarr_forms = [updated_form if f.prefix == 'radarr_new' else f for f in radarr_forms]
                    else:
                        radarr_forms = [form if f.prefix == 'radarr_new' else f for f in radarr_forms]
                else:
                    instance = RadarrInstance.objects.get(id=instance_id)
                    form = RadarrInstanceForm(request.POST, instance=instance, prefix=f'radarr_{instance_id}')
                    form.data = form.data.copy()
                    form.data[f'radarr_{instance_id}-test_connection'] = True
                    if form.is_valid():
                        updated_form = RadarrInstanceForm(
                            initial={
                                'name': form.cleaned_data['name'],
                                'url': form.cleaned_data['url'],
                                'apikey': form.cleaned_data['apikey'],
                                'quality_profile': form.cleaned_data['quality_profile'],
                                'root_folder': form.cleaned_data['root_folder'],
                            },
                            instance=instance,
                            prefix=f'radarr_{instance_id}'
                        )
                        radarr_forms = [updated_form if f.prefix == f'radarr_{instance_id}' else f for f in radarr_forms]
                    else:
                        radarr_forms = [form if f.prefix == f'radarr_{instance_id}' else f for f in radarr_forms]
            
            elif model_type == 'sonarr':
                if instance_id == 'new':
                    form = SonarrInstanceForm(request.POST, prefix='sonarr_new')
                    form.data = form.data.copy()
                    form.data['sonarr_new-test_connection'] = True
                    if form.is_valid():
                        updated_form = SonarrInstanceForm(
                            initial={
                                'name': form.cleaned_data['name'],
                                'url': form.cleaned_data['url'],
                                'apikey': form.cleaned_data['apikey'],
                                'quality_profile': form.cleaned_data['quality_profile'],
                                'root_folder': form.cleaned_data['root_folder'],
                            },
                            prefix='sonarr_new'
                        )
                        sonarr_forms = [updated_form if f.prefix == 'sonarr_new' else f for f in sonarr_forms]
                    else:
                        sonarr_forms = [form if f.prefix == 'sonarr_new' else f for f in sonarr_forms]
                else:
                    instance = SonarrInstance.objects.get(id=instance_id)
                    form = SonarrInstanceForm(request.POST, instance=instance, prefix=f'sonarr_{instance_id}')
                    form.data = form.data.copy()
                    form.data[f'sonarr_{instance_id}-test_connection'] = True
                    if form.is_valid():
                        updated_form = SonarrInstanceForm(
                            initial={
                                'name': form.cleaned_data['name'],
                                'url': form.cleaned_data['url'],
                                'apikey': form.cleaned_data['apikey'],
                                'quality_profile': form.cleaned_data['quality_profile'],
                                'root_folder': form.cleaned_data['root_folder'],
                            },
                            instance=instance,
                            prefix=f'sonarr_{instance_id}'
                        )
                        sonarr_forms = [updated_form if f.prefix == f'sonarr_{instance_id}' else f for f in sonarr_forms]
                    else:
                        sonarr_forms = [form if f.prefix == f'sonarr_{instance_id}' else f for f in sonarr_forms]
    
    context = {
        'mdblist_form': mdblist_form,
        'radarr_forms': radarr_forms,
        'sonarr_forms': sonarr_forms,
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