from django.core.management.base import BaseCommand
from django.utils import timezone
from mdblistrr.models import PlexSyncRun

class Command(BaseCommand):
    help = "Mark Plex sync/reset runs left 'running' by a previous container run as interrupted."

    def handle(self, *args, **options):
        # Runs from the entrypoint before the scheduler and web server start,
        # so no worker thread can exist yet — any 'running' row is an orphan
        # (e.g. the container was restarted mid-sync) and would otherwise block
        # every future run via uniq_plexsyncrun_running.
        updated = PlexSyncRun.objects.filter(status='running').update(
            status='error',
            error_message='Interrupted by restart',
            finished_at=timezone.now(),
        )
        if updated:
            self.stdout.write(f"Marked {updated} interrupted Plex run(s) as error.")
