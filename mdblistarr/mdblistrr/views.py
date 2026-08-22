import logging
import random
import threading
import time
import traceback
import json
import fcntl
import os
import requests as _requests
import xml.etree.ElementTree as ET

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import UserCreationForm
from django.db import connections, transaction
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST, require_http_methods

from .arr import MdblistAPI, RadarrAPI, SonarrAPI, MDBLIST_DEFAULT_CLIENT_ID
from .connect import Connect, sanitize_text
from .models import Preferences, RadarrInstance, SonarrInstance, PlexInstance, PlexSyncRun
from .services import get_mdblistarr, reset_mdblistarr
from .plex_api import PLEX_CLIENT_ID, PLEX_PRODUCT, PLEX_VERSION, PLEX_DEVICE
from .plex_sync import sync_plex_posters, reset_plex_posters, poster_states_in_scope

logger = logging.getLogger(__name__)

MDBLIST_TOKEN_URL = "https://api.mdblist.com/oauth/token/"
MDBLIST_DEVICE_AUTH_URL = "https://api.mdblist.com/oauth/device-authorization/"
MDBLIST_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
MDBLIST_REVOKE_URL = "https://api.mdblist.com/oauth/revoke_token/"

PLEX_PIN_URL = "https://plex.tv/api/v2/pins"
PLEX_RESOURCES_URL = "https://plex.tv/api/v2/resources"


SYNC_HOUR_CHOICES = [(str(h), f"{h:02d}:00 UTC") for h in range(24)]
SYNC_INSTANCE_SCOPE_CHOICES = [
    ('first', 'First configured instance only'),
    ('all', 'All configured instances'),
]


class MDBListForm(forms.Form):
    mdblist_apikey = forms.CharField(
        label='MDBList API Key',
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={'placeholder': 'Leave blank to keep saved API key', 'class': 'form-control'}),
        help_text='Leave blank to keep the saved API key.',
    )
    sync_library_status = forms.BooleanField(
        label='Sync Library Status',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text='Update your MDBList collection based on what is downloaded in Radarr/Sonarr.'
    )
    sync_instance_scope = forms.ChoiceField(
        label='Library Sync Scope',
        choices=SYNC_INSTANCE_SCOPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Choose whether library status sync uses only the first configured Radarr/Sonarr instance or all configured instances.',
    )
    sync_hour = forms.ChoiceField(
        label='Sync Hour (UTC)',
        choices=SYNC_HOUR_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Hour of day (UTC) when Radarr and Sonarr sync runs. Actual sync happens within that hour at a random minute.',
    )

    def __init__(self, *args, oauth_connected=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.oauth_connected = oauth_connected

    def clean(self):
        cleaned_data = super().clean()
        mdblist_apikey = cleaned_data.get('mdblist_apikey')

        if mdblist_apikey and not self.oauth_connected:
            mdblistarr = get_mdblistarr()
            test_instance = mdblistarr.mdblist if mdblistarr.mdblist else MdblistAPI(apikey=mdblist_apikey)
            if not test_instance.test_api(mdblist_apikey):
                self._errors['mdblist_apikey'] = self.error_class(['API key is invalid, unable to connect'])
                self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
            else:
                self.fields['mdblist_apikey'].widget.attrs.update({'class': 'form-control is-valid'})

        return cleaned_data

class MultiValueTagsField(forms.CharField):
    """
    Renders as a checkbox list of tags fetched from Radarr/Sonarr (choices are
    populated dynamically per-instance) and stores the selected tag IDs as a
    comma-separated string, matching how quality_profile/root_folder store
    their selection.
    """
    widget = forms.CheckboxSelectMultiple

    def to_python(self, value):
        if isinstance(value, (list, tuple)):
            return ','.join(v for v in value if v)
        return super().to_python(value)

class InitialAdminSetupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'autocomplete': 'username'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'autocomplete': 'new-password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'autocomplete': 'new-password'})

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
    tags = MultiValueTagsField(
        label='Tags',
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text='Tags applied to everything added through this instance. Create new tags directly in Radarr, then use Test Connection to refresh this list.',
    )

    class Meta:
        model = RadarrInstance
        fields = ['name', 'url', 'apikey', 'quality_profile', 'root_folder', 'minimum_availability', 'tags']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Instance Name', 'class': 'form-control'}),
            'url': forms.TextInput(attrs={'placeholder': 'Radarr URL', 'class': 'form-control'}),
            'apikey': forms.PasswordInput(render_value=False, attrs={'placeholder': 'Leave blank to keep saved API key', 'class': 'form-control'}),
            'quality_profile': forms.Select(attrs={'class': 'form-control'}),
            'root_folder': forms.Select(attrs={'class': 'form-control'}),
            'minimum_availability': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super(RadarrInstanceForm, self).__init__(*args, **kwargs)

        self.fields['apikey'].required = not bool(self.instance and self.instance.pk)
        self.fields['apikey'].help_text = 'Leave blank to keep the saved API key.'

        self.fields['quality_profile'].choices = [('0', 'Select Quality Profile')]
        self.fields['root_folder'].choices = [('0', 'Select Root Folder')]
        self.fields['tags'].choices = []
        self.initial['tags'] = [t for t in (self.instance.tags or '').split(',') if t] if self.instance and self.instance.pk else []

        if self.instance and self.instance.pk and self.instance.url and self.instance.apikey:
            try:
                mdblistarr = get_mdblistarr()
                quality_choices = mdblistarr.get_radarr_quality_profile_choices(self.instance.url, self.instance.apikey)
                root_choices = mdblistarr.get_radarr_root_folder_choices(self.instance.url, self.instance.apikey)
                tag_choices = mdblistarr.get_radarr_tag_choices(self.instance.url, self.instance.apikey)

                self.fields['quality_profile'].choices = quality_choices
                self.fields['root_folder'].choices = root_choices
                self.fields['tags'].choices = tag_choices

                if self.instance.quality_profile and not any(str(self.instance.quality_profile) == choice[0] for choice in quality_choices):
                    self.fields['quality_profile'].choices.append((self.instance.quality_profile, f"Profile {self.instance.quality_profile} (saved)"))

                if self.instance.root_folder and not any(self.instance.root_folder == choice[0] for choice in root_choices):
                    self.fields['root_folder'].choices.append((self.instance.root_folder, self.instance.root_folder))
            except Exception as e:
                logger.error(f"Error initializing RadarrInstanceForm: {sanitize_text(e)}")

class SonarrInstanceForm(forms.ModelForm):
    tags = MultiValueTagsField(
        label='Tags',
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text='Tags applied to everything added through this instance. Create new tags directly in Sonarr, then use Test Connection to refresh this list.',
    )

    class Meta:
        model = SonarrInstance
        fields = ['name', 'url', 'apikey', 'quality_profile', 'root_folder', 'monitor', 'tags']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Instance Name', 'class': 'form-control'}),
            'url': forms.TextInput(attrs={'placeholder': 'Sonarr URL', 'class': 'form-control'}),
            'apikey': forms.PasswordInput(render_value=False, attrs={'placeholder': 'Leave blank to keep saved API key', 'class': 'form-control'}),
            'quality_profile': forms.Select(attrs={'class': 'form-control'}),
            'root_folder': forms.Select(attrs={'class': 'form-control'}),
            'monitor': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super(SonarrInstanceForm, self).__init__(*args, **kwargs)

        self.fields['apikey'].required = not bool(self.instance and self.instance.pk)
        self.fields['apikey'].help_text = 'Leave blank to keep the saved API key.'

        self.fields['quality_profile'].choices = [('0', 'Select Quality Profile')]
        self.fields['root_folder'].choices = [('0', 'Select Root Folder')]
        self.fields['tags'].choices = []
        self.initial['tags'] = [t for t in (self.instance.tags or '').split(',') if t] if self.instance and self.instance.pk else []

        if self.instance and self.instance.pk and self.instance.url and self.instance.apikey:
            try:
                mdblistarr = get_mdblistarr()
                quality_choices = mdblistarr.get_sonarr_quality_profile_choices(self.instance.url, self.instance.apikey)
                root_choices = mdblistarr.get_sonarr_root_folder_choices(self.instance.url, self.instance.apikey)
                tag_choices = mdblistarr.get_sonarr_tag_choices(self.instance.url, self.instance.apikey)

                self.fields['quality_profile'].choices = quality_choices
                self.fields['root_folder'].choices = root_choices
                self.fields['tags'].choices = tag_choices

                if self.instance.quality_profile and not any(str(self.instance.quality_profile) == choice[0] for choice in quality_choices):
                    self.fields['quality_profile'].choices.append((self.instance.quality_profile, f"Profile {self.instance.quality_profile} (saved)"))

                if self.instance.root_folder and not any(self.instance.root_folder == choice[0] for choice in root_choices):
                    self.fields['root_folder'].choices.append((self.instance.root_folder, self.instance.root_folder))
            except Exception as e:
                logger.error(f"Error initializing SonarrInstanceForm: {sanitize_text(e)}")

class PlexInstanceForm(forms.ModelForm):
    library_ids = MultiValueTagsField(
        label='Libraries',
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text='Libraries to stamp posters in. Use Test Connection to refresh this list after adding/removing libraries in Plex.',
    )

    class Meta:
        model = PlexInstance
        fields = ['name', 'url', 'library_ids', 'badge_score_enabled', 'badge_age_rating_enabled', 'sync_audience_rating_enabled']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Instance Name', 'class': 'form-control'}),
            'url': forms.TextInput(attrs={'placeholder': 'Connect with Plex to fill this in', 'class': 'form-control', 'readonly': 'readonly'}),
            'badge_score_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'badge_age_rating_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sync_audience_rating_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(PlexInstanceForm, self).__init__(*args, **kwargs)

        self.fields['library_ids'].choices = []
        self.initial['library_ids'] = [lid for lid in (self.instance.library_ids or '').split(',') if lid] if self.instance and self.instance.pk else []

        if self.instance and self.instance.pk and self.instance.url and self.instance.token:
            try:
                mdblistarr = get_mdblistarr()
                self.fields['library_ids'].choices = mdblistarr.get_plex_library_choices(self.instance.url, self.instance.token)
            except Exception as e:
                logger.error(f"Error initializing PlexInstanceForm: {sanitize_text(e)}")

SETUP_LOCK_PATH = os.environ.get('MDBLISTARR_SETUP_LOCK_PATH', '/usr/src/db/.initial-setup.lock')

def _setup_complete_redirect(request):
    return redirect('home_view' if request.user.is_authenticated and request.user.is_staff else 'login')

class setup_claim_lock:
    def __enter__(self):
        os.makedirs(os.path.dirname(SETUP_LOCK_PATH), exist_ok=True)
        self.handle = open(SETUP_LOCK_PATH, 'a+', encoding='utf-8')
        try:
            os.chmod(SETUP_LOCK_PATH, 0o600)
        except OSError:
            pass
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()

@sensitive_post_parameters('password1', 'password2')
@require_http_methods(["GET", "POST"])
def setup_view(request):
    from .admin_state import usable_administrator_exists
    if usable_administrator_exists():
        return _setup_complete_redirect(request)
    if request.method == 'POST':
        form = InitialAdminSetupForm(request.POST)
        if form.is_valid():
            # There is no user row to lock before setup. This process-wide and
            # cross-process file lock serializes the first-admin claim before
            # the final state check and transactional account creation.
            with setup_claim_lock():
                if usable_administrator_exists():
                    return _setup_complete_redirect(request)
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = True
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()
            login(request, user)
            return redirect('home_view')
    else:
        form = InitialAdminSetupForm()
    return render(request, 'setup.html', {'form': form})

def home_view(request):
    mdblistarr = get_mdblistarr()
    oauth_connected = bool(Preferences.get_secret('mdblist_access_token'))
    oauth_username = Preferences.objects.filter(name='mdblist_username').values_list('value', flat=True).first() or ''
    oauth_name = Preferences.objects.filter(name='mdblist_name').values_list('value', flat=True).first() or ''
    oauth_plan = Preferences.objects.filter(name='mdblist_plan').values_list('value', flat=True).first() or ''

    sync_library_pref = Preferences.objects.filter(name='sync_library_status').first()
    sync_instance_scope_pref = Preferences.objects.filter(name='sync_instance_scope').first()
    sync_hour_pref = Preferences.objects.filter(name='sync_hour').first()
    if not sync_hour_pref:
        random_hour = str(random.randint(0, 23))
        sync_hour_pref, _ = Preferences.objects.update_or_create(
            name='sync_hour', defaults={'value': random_hour}
        )
    mdblist_form = MDBListForm(
        oauth_connected=oauth_connected,
        initial={
            'mdblist_apikey': '',
            'sync_library_status': sync_library_pref and sync_library_pref.value == '1',
            'sync_instance_scope': sync_instance_scope_pref.value if sync_instance_scope_pref else 'first',
            'sync_hour': sync_hour_pref.value,
        },
    )
    
    radarr_instances = RadarrInstance.objects.all()
    sonarr_instances = SonarrInstance.objects.all()
    
    radarr_choices = [('new', '--- Add New Radarr Server ---')]
    radarr_choices.extend([(str(instance.id), instance.name) for instance in radarr_instances])
    
    sonarr_choices = [('new', '--- Add New Sonarr Server ---')]
    sonarr_choices.extend([(str(instance.id), instance.name) for instance in sonarr_instances])

    plex_instances = PlexInstance.objects.all()
    plex_choices = [('new', '--- Add New Plex Server ---')]
    plex_choices.extend([(str(instance.id), instance.name) for instance in plex_instances])

    radarr_selection_form = ServerSelectionForm(choices=radarr_choices, prefix='radarr_select')
    sonarr_selection_form = ServerSelectionForm(choices=sonarr_choices, prefix='sonarr_select')
    plex_selection_form = ServerSelectionForm(choices=plex_choices, prefix='plex_select')

    radarr_form = RadarrInstanceForm()
    sonarr_form = SonarrInstanceForm()
    plex_form = PlexInstanceForm()

    active_radarr_id = request.session.get('active_radarr_id')
    active_sonarr_id = request.session.get('active_sonarr_id')
    active_plex_id = request.session.get('active_plex_id')

    # Restore form for the previously active instance on fresh GET
    if request.method == "GET":
        if active_radarr_id and active_radarr_id != 'new':
            try:
                instance = RadarrInstance.objects.get(id=active_radarr_id)
                radarr_form = RadarrInstanceForm(instance=instance)
            except RadarrInstance.DoesNotExist:
                active_radarr_id = None
                request.session.pop('active_radarr_id', None)
        if active_sonarr_id and active_sonarr_id != 'new':
            try:
                instance = SonarrInstance.objects.get(id=active_sonarr_id)
                sonarr_form = SonarrInstanceForm(instance=instance)
            except SonarrInstance.DoesNotExist:
                active_sonarr_id = None
                request.session.pop('active_sonarr_id', None)
        if active_plex_id and active_plex_id != 'new':
            try:
                instance = PlexInstance.objects.get(id=active_plex_id)
                plex_form = PlexInstanceForm(instance=instance)
            except PlexInstance.DoesNotExist:
                active_plex_id = None
                request.session.pop('active_plex_id', None)

    if request.method == "POST":
        form_type = request.POST.get('form_type', '')
        if form_type.startswith('mdblist'):
            request.session['active_tab'] = 'mdblist'
        elif form_type.startswith('radarr'):
            request.session['active_tab'] = 'radarr'
        elif form_type.startswith('sonarr'):
            request.session['active_tab'] = 'sonarr'
        elif form_type.startswith('plex'):
            request.session['active_tab'] = 'plex'

        if form_type == 'mdblist':
            mdblist_form = MDBListForm(request.POST, oauth_connected=oauth_connected)
            if mdblist_form.is_valid():
                apikey = mdblist_form.cleaned_data.get('mdblist_apikey', '').strip()
                if apikey and not oauth_connected:
                    Preferences.set_secret('mdblist_apikey', apikey)
                Preferences.objects.update_or_create(
                    name='sync_library_status',
                    defaults={'value': '1' if mdblist_form.cleaned_data.get('sync_library_status') else '0'}
                )
                Preferences.objects.update_or_create(
                    name='sync_instance_scope',
                    defaults={'value': mdblist_form.cleaned_data.get('sync_instance_scope', 'first')}
                )
                Preferences.objects.update_or_create(
                    name='sync_hour',
                    defaults={'value': mdblist_form.cleaned_data.get('sync_hour', '10')}
                )
                reset_mdblistarr()
                messages.success(request, "MDBList configuration saved successfully!")
                return HttpResponseRedirect(reverse('home_view'))
        
        elif form_type == 'radarr_select':
            radarr_selection_form = ServerSelectionForm(request.POST, choices=radarr_choices, prefix='radarr_select')
            if radarr_selection_form.is_valid():
                server_id = radarr_selection_form.cleaned_data['server_selection']
                if server_id != 'new':
                    active_radarr_id = server_id
                    request.session['active_radarr_id'] = server_id
                    instance = RadarrInstance.objects.get(id=server_id)
                    radarr_form = RadarrInstanceForm(instance=instance)
                else:
                    active_radarr_id = 'new'
                    request.session['active_radarr_id'] = 'new'
                    radarr_form = RadarrInstanceForm()

        elif form_type == 'sonarr_select':
            sonarr_selection_form = ServerSelectionForm(request.POST, choices=sonarr_choices, prefix='sonarr_select')
            if sonarr_selection_form.is_valid():
                server_id = sonarr_selection_form.cleaned_data['server_selection']
                if server_id != 'new':
                    active_sonarr_id = server_id
                    request.session['active_sonarr_id'] = server_id
                    instance = SonarrInstance.objects.get(id=server_id)
                    sonarr_form = SonarrInstanceForm(instance=instance)
                else:
                    active_sonarr_id = 'new'
                    request.session['active_sonarr_id'] = 'new'
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

                mdblistarr = get_mdblistarr()
                if not instance.apikey and instance_id and instance_id != 'new':
                    instance.apikey = RadarrInstance.objects.get(id=instance_id).apikey
                connection = mdblistarr.test_radarr_connection(instance.url, instance.apikey)
                
                if connection['status']:
                    instance.save()
                    request.session['active_radarr_id'] = str(instance.id)
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

                mdblistarr = get_mdblistarr()
                if not instance.apikey and instance_id and instance_id != 'new':
                    instance.apikey = SonarrInstance.objects.get(id=instance_id).apikey
                connection = mdblistarr.test_sonarr_connection(instance.url, instance.apikey)
                
                if connection['status']:
                    instance.save()
                    request.session['active_sonarr_id'] = str(instance.id)
                    messages.success(request, "Sonarr configuration saved successfully!")
                    return HttpResponseRedirect(reverse('home_view'))
                else:
                    sonarr_form.add_error('apikey', 'Unable to connect to Sonarr')
                    sonarr_form.fields['apikey'].widget.attrs.update({'class': 'form-control is-invalid'})
        
        elif form_type == 'radarr_delete':
            instance_id = request.POST.get('instance_id')
            if instance_id:
                RadarrInstance.objects.filter(id=instance_id).delete()
                request.session.pop('active_radarr_id', None)
                active_radarr_id = None
                return HttpResponseRedirect(reverse('home_view'))

        elif form_type == 'sonarr_delete':
            instance_id = request.POST.get('instance_id')
            if instance_id:
                SonarrInstance.objects.filter(id=instance_id).delete()
                request.session.pop('active_sonarr_id', None)
                active_sonarr_id = None
                return HttpResponseRedirect(reverse('home_view'))

        elif form_type == 'plex_select':
            plex_selection_form = ServerSelectionForm(request.POST, choices=plex_choices, prefix='plex_select')
            if plex_selection_form.is_valid():
                server_id = plex_selection_form.cleaned_data['server_selection']
                if server_id != 'new':
                    active_plex_id = server_id
                    request.session['active_plex_id'] = server_id
                    instance = PlexInstance.objects.get(id=server_id)
                    plex_form = PlexInstanceForm(instance=instance)
                else:
                    active_plex_id = 'new'
                    request.session['active_plex_id'] = 'new'
                    plex_form = PlexInstanceForm()

        elif form_type == 'plex_save':
            instance_id = request.POST.get('instance_id')

            if instance_id and instance_id != 'new':
                instance = get_object_or_404(PlexInstance, id=instance_id)
                plex_form = PlexInstanceForm(request.POST, instance=instance)
                active_plex_id = instance_id
            else:
                plex_form = PlexInstanceForm(request.POST)

            if plex_form.is_valid():
                instance = plex_form.save(commit=False)

                pending_token = request.session.get('plex_pending_token')
                if pending_token:
                    instance.token = pending_token
                elif instance_id and instance_id != 'new':
                    instance.token = PlexInstance.objects.get(id=instance_id).token
                else:
                    plex_form.add_error(None, 'Connect with Plex before saving.')

                if not plex_form.errors:
                    mdblistarr = get_mdblistarr()
                    connection = mdblistarr.test_plex_connection(instance.url, instance.token)

                    if connection['status']:
                        instance.save()
                        request.session.pop('plex_pending_token', None)
                        request.session['active_plex_id'] = str(instance.id)
                        messages.success(request, "Plex configuration saved successfully!")
                        return HttpResponseRedirect(reverse('home_view'))
                    else:
                        plex_form.add_error('url', 'Unable to connect to Plex')

        elif form_type == 'plex_delete':
            instance_id = request.POST.get('instance_id')
            if instance_id:
                PlexInstance.objects.filter(id=instance_id).delete()
                request.session.pop('active_plex_id', None)
                active_plex_id = None
                return HttpResponseRedirect(reverse('home_view'))

    if active_radarr_id:
        radarr_selection_form.initial = {'server_selection': active_radarr_id}
    if active_sonarr_id:
        sonarr_selection_form.initial = {'server_selection': active_sonarr_id}
    if active_plex_id:
        plex_selection_form.initial = {'server_selection': active_plex_id}

    context = {
        'mdblist_form': mdblist_form,
        'radarr_selection_form': radarr_selection_form,
        'sonarr_selection_form': sonarr_selection_form,
        'plex_selection_form': plex_selection_form,
        'radarr_form': radarr_form,
        'sonarr_form': sonarr_form,
        'plex_form': plex_form,
        'active_radarr_id': active_radarr_id,
        'active_sonarr_id': active_sonarr_id,
        'active_plex_id': active_plex_id,
        'plex_instances': plex_instances,
        'plex_has_synced_items': poster_states_in_scope().exists(),
        'active_tab': request.session.get('active_tab', 'mdblist'),
        'oauth_connected': oauth_connected,
        'oauth_username': oauth_username,
        'oauth_name': oauth_name,
        'oauth_plan': oauth_plan,
    }

    return render(request, "index.html", context)


@require_POST
def oauth_device_start(request):
    client_id_pref = Preferences.objects.filter(name='mdblist_client_id').first()
    client_id = (client_id_pref.value if client_id_pref else '') or MDBLIST_DEFAULT_CLIENT_ID

    try:
        r = _requests.post(MDBLIST_DEVICE_AUTH_URL, data={'client_id': client_id, 'scope': 'write'})
        data = r.json()
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    if not data.get('device_code'):
        return JsonResponse({'error': data.get('error_description') or data.get('error', 'Unknown error')}, status=400)

    request.session['oauth_device_code'] = data['device_code']
    request.session['oauth_device_client_id'] = client_id

    return JsonResponse({
        'user_code': data['user_code'],
        'verification_uri': data['verification_uri'],
        'expires_in': data.get('expires_in', 300),
        'interval': data.get('interval', 5),
    })


@require_POST
def oauth_device_poll(request):
    device_code = request.session.get('oauth_device_code')
    client_id = request.session.get('oauth_device_client_id')

    if not device_code or not client_id:
        return JsonResponse({'status': 'error', 'message': 'Session expired, please start over.'})

    try:
        r = _requests.post(MDBLIST_TOKEN_URL, data={
            'grant_type': MDBLIST_DEVICE_GRANT_TYPE,
            'device_code': device_code,
            'client_id': client_id,
        })
        data = r.json()
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

    if data.get('access_token'):
        expires_at = int(time.time() + data.get('expires_in', 2592000))
        access_token = data['access_token']
        Preferences.set_secret('mdblist_access_token', access_token)
        Preferences.set_secret('mdblist_refresh_token', data.get('refresh_token', ''))
        Preferences.objects.update_or_create(name='mdblist_token_expires_at', defaults={'value': str(expires_at)})
        Preferences.clear_secret('mdblist_apikey')
        request.session.pop('oauth_device_code', None)
        request.session.pop('oauth_device_client_id', None)

        try:
            user_resp = _requests.get(
                'https://api.mdblist.com/user',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=5,
            )
            user_data = user_resp.json()
            Preferences.objects.update_or_create(name='mdblist_username', defaults={'value': user_data.get('username') or ''})
            Preferences.objects.update_or_create(name='mdblist_name', defaults={'value': user_data.get('name') or ''})
            Preferences.objects.update_or_create(name='mdblist_plan', defaults={'value': user_data.get('plan') or ''})
        except Exception:
            pass

        reset_mdblistarr()
        return JsonResponse({'status': 'complete'})

    error = data.get('error', '')
    if error == 'authorization_pending':
        return JsonResponse({'status': 'pending'})
    if error == 'slow_down':
        return JsonResponse({'status': 'slow_down'})
    if error == 'expired_token':
        return JsonResponse({'status': 'expired'})
    if error == 'access_denied':
        return JsonResponse({'status': 'denied'})
    return JsonResponse({'status': 'error', 'message': data.get('error_description') or error or 'Unknown error'})


@require_POST
def oauth_disconnect(request):
    token = Preferences.get_secret('mdblist_access_token')
    client_id_pref = Preferences.objects.filter(name='mdblist_client_id').first()
    if token:
        try:
            _requests.post(MDBLIST_REVOKE_URL, data={
                'token': token,
                'client_id': (client_id_pref.value if client_id_pref else '') or MDBLIST_DEFAULT_CLIENT_ID,
            }, timeout=5)
        except Exception:
            pass
    Preferences.clear_secret('mdblist_access_token')
    Preferences.clear_secret('mdblist_refresh_token')
    Preferences.objects.filter(name='mdblist_token_expires_at').update(value='')
    Preferences.objects.filter(name='mdblist_username').update(value='')
    Preferences.objects.filter(name='mdblist_name').update(value='')
    Preferences.objects.filter(name='mdblist_plan').update(value='')
    reset_mdblistarr()
    messages.success(request, "Disconnected from MDBList OAuth.")
    return redirect('home_view')

def _fetch_plex_servers(auth_token):
    """
    List discovered Plex Media Server connections for this account, local and
    remote alike (mdblistarr typically runs on the same network as Plex,
    unlike mdblist.com's own hosted Plex integration).
    """
    headers = {
        'X-Plex-Token': auth_token,
        'X-Plex-Client-Identifier': PLEX_CLIENT_ID,
    }
    try:
        r = _requests.get(PLEX_RESOURCES_URL, headers=headers, params={'includeHttps': 1, 'includeRelay': 1}, timeout=10)
        root = ET.fromstring(r.text)
    except Exception:
        return []

    options = []
    for resource in root.findall('resource'):
        if resource.attrib.get('product') != 'Plex Media Server':
            continue
        name = resource.attrib.get('name') or 'Plex Server'
        conn_group = resource.find('connections')
        if conn_group is None:
            continue
        conns = list(conn_group.findall('connection'))
        conns.sort(key=lambda c: c.attrib.get('local') != '1')  # local connections first
        for conn in conns:
            uri = conn.attrib.get('uri')
            if not uri:
                continue
            local = conn.attrib.get('local') == '1'
            options.append({
                'uri': uri,
                'name': name,
                'label': f"{name} — {uri}{' (local)' if local else ''}",
            })
    return options


@require_POST
def plex_auth_start(request):
    headers = {
        'X-Plex-Client-Identifier': PLEX_CLIENT_ID,
        'X-Plex-Product': PLEX_PRODUCT,
        'X-Plex-Version': PLEX_VERSION,
        'X-Plex-Device': PLEX_DEVICE,
    }
    try:
        r = _requests.post(PLEX_PIN_URL, headers=headers, params={'strong': 'false'}, timeout=10)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    if r.status_code != 201:
        return JsonResponse({'error': 'Failed to start Plex authorization'}, status=400)

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return JsonResponse({'error': 'Unexpected response from Plex'}, status=502)

    pin_id = root.attrib.get('id')
    pin_code = root.attrib.get('code')
    if not pin_id or not pin_code:
        return JsonResponse({'error': 'Failed to start Plex authorization'}, status=400)

    request.session['plex_pin_id'] = pin_id

    return JsonResponse({
        'pin_code': pin_code,
        'auth_url': f'https://plex.tv/link?pin={pin_code}',
    })


@require_POST
def plex_auth_poll(request):
    pin_id = request.session.get('plex_pin_id')
    if not pin_id:
        return JsonResponse({'status': 'error', 'message': 'Session expired, please start over.'})

    headers = {
        'X-Plex-Client-Identifier': PLEX_CLIENT_ID,
        'X-Plex-Product': PLEX_PRODUCT,
        'X-Plex-Version': PLEX_VERSION,
        'X-Plex-Device': PLEX_DEVICE,
    }
    try:
        r = _requests.get(f'{PLEX_PIN_URL}/{pin_id}', headers=headers, timeout=10)
        root = ET.fromstring(r.text)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

    auth_token = root.attrib.get('authToken')
    if not auth_token:
        return JsonResponse({'status': 'pending'})

    request.session.pop('plex_pin_id', None)
    request.session['plex_pending_token'] = auth_token

    servers = _fetch_plex_servers(auth_token)
    return JsonResponse({'status': 'complete', 'servers': servers})


@csrf_exempt
def test_plex_connection(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        instance_id = data.get('instance_id')
        url = data.get('url')

        if instance_id and instance_id != 'new':
            instance = get_object_or_404(PlexInstance, id=instance_id)
            url = url or instance.url
            token = instance.token
        else:
            token = request.session.get('plex_pending_token')

        if not url or not token:
            return JsonResponse({'status': 'error', 'message': 'Connect with Plex first'})

        mdblistarr = get_mdblistarr()
        result = mdblistarr.test_plex_connection(url, token)

        if result['status']:
            libraries = mdblistarr.get_plex_library_choices(url, token)
            return JsonResponse({'status': 'success', 'version': result['version'], 'libraries': libraries})
        else:
            return JsonResponse({'status': 'error', 'message': 'Unable to connect to Plex'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


def _plex_run_status_payload(run):
    return {
        'status': run.status,
        'kind': run.kind,
        'total_items': run.total_items,
        'processed_items': run.processed_items,
        'stamped': run.stamped,
        'skipped': run.skipped,
        'errors': run.errors,
        'current_title': run.current_title,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'error_message': run.error_message,
    }


def _run_plex_job_in_background(job_func, run):
    try:
        job_func(run=run)
    finally:
        # This thread outlives the request that started it; make sure it
        # doesn't hold a DB connection open past the job finishing.
        connections.close_all()


def _start_plex_job(kind, job_func):
    """
    Creates the PlexSyncRun row synchronously (in the request thread) before
    spawning the background worker thread — otherwise a request arriving
    right after this one could run its own "is anything running" check
    before the spawned thread has gotten around to creating that row, and
    wrongly conclude nothing is running.
    """
    latest = PlexSyncRun.objects.order_by('-started_at').first()
    if latest and latest.status == 'running':
        return JsonResponse(_plex_run_status_payload(latest))

    run = PlexSyncRun.objects.create(status='running', started_at=timezone.now(), kind=kind)
    threading.Thread(target=_run_plex_job_in_background, args=(job_func, run), daemon=True).start()
    return JsonResponse(_plex_run_status_payload(run))


@require_POST
def plex_sync_start(request):
    if not PlexInstance.objects.exists():
        latest = PlexSyncRun.objects.order_by('-started_at').first()
        if latest and latest.status == 'running':
            return JsonResponse(_plex_run_status_payload(latest))
        return JsonResponse({'status': 'error', 'message': 'No Plex servers configured'}, status=400)

    return _start_plex_job('sync', sync_plex_posters)


@require_POST
def plex_reset_start(request):
    if not poster_states_in_scope().exists():
        latest = PlexSyncRun.objects.order_by('-started_at').first()
        if latest and latest.status == 'running':
            return JsonResponse(_plex_run_status_payload(latest))
        return JsonResponse({'status': 'error', 'message': 'Nothing to reset in your currently selected libraries'}, status=400)

    return _start_plex_job('reset', reset_plex_posters)


def plex_sync_status(request):
    run = PlexSyncRun.objects.order_by('-started_at').first()
    if not run:
        return JsonResponse({'status': 'idle'})
    return JsonResponse(_plex_run_status_payload(run))


@require_POST
def plex_sync_cancel(request):
    updated = PlexSyncRun.objects.filter(status='running').update(cancel_requested=True)
    return JsonResponse({'status': 'cancelling' if updated else 'idle'})


@csrf_exempt
def test_radarr_connection(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        url = data.get('url')
        apikey = data.get('apikey')
        instance_id = data.get('instance_id')
        if not apikey and instance_id and instance_id != 'new':
            apikey = get_object_or_404(RadarrInstance, id=instance_id).apikey

        mdblistarr = get_mdblistarr()
        result = mdblistarr.test_radarr_connection(url, apikey)
        
        if result['status']:
            quality_profiles = mdblistarr.get_radarr_quality_profile_choices(url, apikey)
            root_folders = mdblistarr.get_radarr_root_folder_choices(url, apikey)
            tags = mdblistarr.get_radarr_tag_choices(url, apikey)

            return JsonResponse({
                'status': 'success',
                'version': result['version'],
                'quality_profiles': quality_profiles,
                'root_folders': root_folders,
                'tags': tags
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
        instance_id = data.get('instance_id')
        if not apikey and instance_id and instance_id != 'new':
            apikey = get_object_or_404(SonarrInstance, id=instance_id).apikey

        mdblistarr = get_mdblistarr()
        result = mdblistarr.test_sonarr_connection(url, apikey)
        
        if result['status']:
            quality_profiles = mdblistarr.get_sonarr_quality_profile_choices(url, apikey)
            root_folders = mdblistarr.get_sonarr_root_folder_choices(url, apikey)
            tags = mdblistarr.get_sonarr_tag_choices(url, apikey)

            return JsonResponse({
                'status': 'success',
                'version': result['version'],
                'quality_profiles': quality_profiles,
                'root_folders': root_folders,
                'tags': tags
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Unable to connect to Sonarr'
            })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


@require_POST
def set_active_tab(request):
    try:
        data = json.loads(request.body)
        tab = data.get("tab")
        if tab in {"mdblist", "radarr", "sonarr", "plex"}:
            request.session["active_tab"] = tab
            return JsonResponse({"status": "ok"})
    except json.JSONDecodeError:
        pass
    return JsonResponse({"status": "error", "message": "Invalid tab"}, status=400)
