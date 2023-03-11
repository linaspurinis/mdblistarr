from django.shortcuts import render
from django.views.generic import ListView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django import forms
from .models import Preferences
from .connect import Connect
from .arr import SonarrAPI
from .arr import RadarrAPI
from .arr import MdblistAPI
from django.core.exceptions import ValidationError
import traceback

class MDBListarr():
    def __init__(self):
        self.mdblist_apikey = None
        self.radarr_url = None 
        self.radarr_apikey = None
        self.radarr_quality_profile = None
        self.radarr_root_folder = None
        self.sonarr_url = None 
        self.sonarr_apikey = None
        self.sonarr_quality_profile = None
        self.sonarr_root_folder = None
        self.radarr = None
        self.sonarr = None
        self.mdblist = None
        self._get_config()

        if self.radarr_url and self.radarr_apikey:
            self.radarr = RadarrAPI(self.radarr_url, self.radarr_apikey)
        if self.sonarr_url and self.sonarr_apikey:
            self.sonarr = SonarrAPI(self.sonarr_url, self.sonarr_apikey)
        if self.mdblist_apikey:
            self.mdblist = MdblistAPI(self.mdblist_apikey)

    def _get_config(self):
        pref = Preferences.objects.filter(name='mdblist_apikey').first()
        if pref is not None: 
            self.mdblist_apikey = pref.value

        pref = Preferences.objects.filter(name='radarr_apikey').first()
        if pref is not None:
            self.radarr_apikey = pref.value

        pref = Preferences.objects.filter(name='radarr_url').first()
        if pref is not None:
            self.radarr_url = pref.value

        pref = Preferences.objects.filter(name='radarr_quality_profile').first()
        if pref is not None:
            self.radarr_quality_profile = pref.value

        pref = Preferences.objects.filter(name='radarr_root_folder').first()
        if pref is not None:
            self.radarr_root_folder = pref.value

        pref = Preferences.objects.filter(name='sonarr_apikey').first()
        if pref is not None:
            self.sonarr_apikey = pref.value
            
        pref = Preferences.objects.filter(name='sonarr_url').first()
        if pref is not None:
            self.sonarr_url = pref.value

        pref = Preferences.objects.filter(name='sonarr_quality_profile').first()
        if pref is not None:
            self.sonarr_quality_profile = pref.value

        pref = Preferences.objects.filter(name='sonarr_root_folder').first()
        if pref is not None:
            self.sonarr_root_folder = pref.value

    def get_radarr_quality_profile_choices(self):
        choices_list = []
        if self.radarr is not None:
            quality_profiles = self.radarr.get_quality_profile()
            choices_list = [('0', 'Select Default Quality Profile')]
            for profile in quality_profiles:
                choices_list.append((profile['id'], profile['name']))
        return choices_list

    def get_radarr_root_folder_choices(self):
        choices_list = []
        if self.radarr is not None:
            quality_profiles = self.radarr.get_root_folder()
            choices_list = [('0', 'Select Default Root Folder')]
            for profile in quality_profiles:
                choices_list.append((profile['path'], profile['path']))
        return choices_list

    def get_sonarr_quality_profile_choices(self):
        choices_list = []
        if self.sonarr is not None:
            quality_profiles = self.sonarr.get_quality_profile()
            choices_list = [('0', 'Select Default Quality Profile')]
            for profile in quality_profiles:
                choices_list.append((profile['id'], profile['name']))
        return choices_list

    def get_sonarr_root_folder_choices(self):
        choices_list = []
        if self.sonarr is not None:
            quality_profiles = self.sonarr.get_root_folder()
            choices_list = [('0', 'Select Default Root Folder')]
            for profile in quality_profiles:
                choices_list.append((profile['path'], profile['path']))
        return choices_list


mdblistarr = MDBListarr()

class UserInfoForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(UserInfoForm, self).__init__(*args, **kwargs)
        self.update_drop_fields()

    #clean validation
    def clean(self):
        super(UserInfoForm, self).clean()

        found_error = False
        
        mdblist_apikey = self.cleaned_data.get('mdblist_apikey')
        if mdblistarr.mdblist is None:
            mdblistarr.mdblist = MdblistAPI(mdblist_apikey)
        if not mdblistarr.mdblist.test_api(mdblist_apikey):
            self._errors['mdblist_apikey'] = self.error_class(['API key is invalid, unable to connect'])
            self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
            found_error = True
        else:
            self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-valid'})

        radarr_apikey = self.cleaned_data.get('radarr_apikey')
        radarr_url = self.cleaned_data.get('radarr_url')
        if radarr_apikey and radarr_url:
            radarr = RadarrAPI(radarr_url, radarr_apikey)
            radarr_status = radarr.get_status()
            if radarr_status['status'] == 1:
                mdblistarr.radarr = radarr
                self.fields['radarr_apikey'].widget.attrs.update({'class': 'form-control is-valid'})

                if self.cleaned_data['radarr_quality_profile'] == '' or self.cleaned_data['radarr_quality_profile'] == '0':
                    self._errors['radarr_quality_profile'] = self.error_class(['Select profile'])
                    self.fields['radarr_quality_profile'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True
                if self.cleaned_data['radarr_root_folder'] == '' or self.cleaned_data['radarr_root_folder'] == '0':
                    self._errors['radarr_root_folder'] = self.error_class(['Select root folder'])
                    self.fields['radarr_root_folder'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True

            else:
                self._errors['radarr_apikey'] = self.error_class(['Unable to connect'])
                self.fields['radarr_apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
                mdblistarr.radarr = None
                found_error = True
        else:
            mdblistarr.radarr = None

        sonarr_apikey = self.cleaned_data.get('sonarr_apikey')
        sonarr_url = self.cleaned_data.get('sonarr_url')
        if sonarr_apikey and sonarr_url:
            sonarr = SonarrAPI(sonarr_url, sonarr_apikey)
            sonarr_status = sonarr.get_status()
            if sonarr_status['status'] == 1:
                mdblistarr.sonarr = sonarr
                self.fields['sonarr_apikey'].widget.attrs.update({'class': 'form-control is-valid'})
    
                if self.cleaned_data['sonarr_quality_profile'] == '' or self.cleaned_data['sonarr_quality_profile'] == '0':
                    self._errors['sonarr_quality_profile'] = self.error_class(['Select profile'])
                    self.fields['sonarr_quality_profile'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True
                if self.cleaned_data['sonarr_root_folder'] == '' or self.cleaned_data['sonarr_root_folder'] == '0':
                    self._errors['sonarr_root_folder'] = self.error_class(['Select root folder'])
                    self.fields['sonarr_root_folder'].widget.attrs.update({'class': 'form-control is-invalid'})
                    found_error = True

            else:
                self._errors['sonarr_apikey'] = self.error_class(['Unable to connect'])
                self.fields['sonarr_apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
                mdblistarr.sonarr = None
                found_error = True
        else:
            mdblistarr.sonarr = None

        if found_error:
            self.add_error(None, "Correct all errors to save the changes")

        return self.cleaned_data

    def update_drop_fields(self):
        if mdblistarr.radarr is not None:
            self.fields['radarr_quality_profile'].disabled = False
            self.fields['radarr_root_folder'].disabled = False
            self.fields['radarr_quality_profile'].choices = mdblistarr.get_radarr_quality_profile_choices()
            self.fields['radarr_root_folder'].choices = mdblistarr.get_radarr_root_folder_choices()
            radarr_status = mdblistarr.radarr.get_status()
            if radarr_status['status'] == 1:
                self.fields['radarr_apikey'].help_text = f"{radarr_status['json']['instanceName']} {radarr_status['json']['version']}"
        else:
            self.fields['radarr_quality_profile'].disabled = True
            self.fields['radarr_root_folder'].disabled = True

        if mdblistarr.sonarr is not None:
            self.fields['sonarr_quality_profile'].disabled = False
            self.fields['sonarr_root_folder'].disabled = False
            self.fields['sonarr_quality_profile'].choices = mdblistarr.get_sonarr_quality_profile_choices()
            self.fields['sonarr_root_folder'].choices = mdblistarr.get_sonarr_root_folder_choices()
            sonarr_status = mdblistarr.sonarr.get_status()
            if sonarr_status['status'] == 1:
                self.fields['sonarr_apikey'].help_text = f"{sonarr_status['json']['instanceName']} {sonarr_status['json']['version']}"
        else:
            self.fields['sonarr_quality_profile'].disabled = True
            self.fields['sonarr_root_folder'].disabled = True


    radarr_quality_profile = forms.ChoiceField(label='Select Quality Profile', required=False, widget=forms.Select(attrs={'placeholder': 'Name', 'class': 'form-control'}), choices=mdblistarr.get_radarr_quality_profile_choices())
    radarr_root_folder = forms.ChoiceField(label='Select Root Folder', required=False, widget=forms.Select(attrs={'placeholder': 'Name', 'class': 'form-control'}), choices=mdblistarr.get_radarr_root_folder_choices())
    sonarr_quality_profile = forms.ChoiceField(label='Select Quality Profile', required=False, widget=forms.Select(attrs={'placeholder': 'Name', 'class': 'form-control'}), choices=mdblistarr.get_sonarr_quality_profile_choices())
    sonarr_root_folder = forms.ChoiceField(label='Select Root Folder', required=False, widget=forms.Select(attrs={'placeholder': 'Name', 'class': 'form-control'}), choices=mdblistarr.get_sonarr_root_folder_choices())

    mdblist_apikey = forms.CharField(label='MDBList API Key', widget=forms.TextInput(attrs={'placeholder': 'Enter your mdblist.com API key', 'class': 'form-control'}))
    radarr_apikey = forms.CharField(label='Radarr API Key', required=False, widget=forms.TextInput(attrs={'placeholder': 'Enter your Radarr API key', 'class': 'form-control'}))
    radarr_url = forms.CharField(label='Radarr URL', required=False, widget=forms.TextInput(attrs={'placeholder': 'Enter your Radarr URL', 'class': 'form-control'}))
    sonarr_apikey = forms.CharField(label='Sonarr API Key', required=False, widget=forms.TextInput(attrs={'placeholder': 'Enter your Sonarr API key', 'class': 'form-control'}))
    sonarr_url = forms.CharField(label='Sonarr URL', required=False, widget=forms.TextInput(attrs={'placeholder': 'Enter your Sonarr URL', 'class': 'form-control'}))

def home_view(request):

    if request.method == "POST":
        form = UserInfoForm(request.POST)
        if form.is_valid():
            Preferences.objects.update_or_create(name='mdblist_apikey', defaults={'value': form.cleaned_data['mdblist_apikey']},)
            mdblistarr.mdblist_apikey = form.cleaned_data['mdblist_apikey']
            Preferences.objects.update_or_create(name='radarr_apikey', defaults={'value': form.cleaned_data['radarr_apikey']},)
            mdblistarr.radarr_apikey = form.cleaned_data['radarr_apikey']
            Preferences.objects.update_or_create(name='radarr_url', defaults={'value': form.cleaned_data['radarr_url']},)
            mdblistarr.radarr_url = form.cleaned_data['radarr_url']
            Preferences.objects.update_or_create(name='radarr_root_folder', defaults={'value': form.cleaned_data['radarr_root_folder']},)
            mdblistarr.radarr_root_folder = form.cleaned_data['radarr_root_folder']
            Preferences.objects.update_or_create(name='radarr_quality_profile', defaults={'value': form.cleaned_data['radarr_quality_profile']},)
            mdblistarr.radarr_quality_profile = form.cleaned_data['radarr_quality_profile']
            Preferences.objects.update_or_create(name='sonarr_quality_profile', defaults={'value': form.cleaned_data['sonarr_quality_profile']},)
            mdblistarr.sonarr_quality_profile = form.cleaned_data['sonarr_quality_profile']
            Preferences.objects.update_or_create(name='sonarr_root_folder', defaults={'value': form.cleaned_data['sonarr_root_folder']},)
            mdblistarr.sonarr_root_folder = form.cleaned_data['sonarr_root_folder']
            Preferences.objects.update_or_create(name='sonarr_apikey', defaults={'value': form.cleaned_data['sonarr_apikey']},)
            mdblistarr.sonarr_apikey = form.cleaned_data['sonarr_apikey']
            Preferences.objects.update_or_create(name='sonarr_url', defaults={'value': form.cleaned_data['sonarr_url']},)
            mdblistarr.sonarr_url = form.cleaned_data['sonarr_url']

            form.update_drop_fields()
            return render(request, "index.html", {'form': form, })
        else:
            form.update_drop_fields()
            return render(request, "index.html", {'form': form, })
    else:
        form = UserInfoForm(initial={   'mdblist_apikey': mdblistarr.mdblist_apikey, 
                                        'radarr_apikey': mdblistarr.radarr_apikey, 
                                        'radarr_url': mdblistarr.radarr_url, 
                                        'radarr_quality_profile': mdblistarr.radarr_quality_profile, 
                                        'radarr_root_folder': mdblistarr.radarr_root_folder, 
                                        'sonarr_apikey': mdblistarr.sonarr_apikey, 
                                        'sonarr_url': mdblistarr.sonarr_url,
                                        'sonarr_quality_profile': mdblistarr.sonarr_quality_profile, 
                                        'sonarr_root_folder': mdblistarr.sonarr_root_folder
                                    })
        return render(request, "index.html", {'form': form, })


