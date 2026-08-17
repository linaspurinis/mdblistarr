from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations.fields import AddField
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = (
        "Mark migrations as applied when the columns they would add already exist. "
        "Bridges deployments whose entrypoint used to delete and regenerate "
        "migrations on every boot: that created columns without Django ever "
        "recording the individual migration as applied, which then made a later "
        "plain `migrate` try to add the same column twice."
    )

    def handle(self, *args, **options):
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()
        loader = MigrationLoader(connection, ignore_no_migrations=True)

        with connection.cursor() as cursor:
            existing_tables = set(connection.introspection.table_names(cursor))

        for (app_label, name), migration in loader.disk_migrations.items():
            if (app_label, name) in applied:
                continue

            add_field_ops = [op for op in migration.operations if isinstance(op, AddField)]
            if not add_field_ops or len(add_field_ops) != len(migration.operations):
                # Only reconcile migrations made up entirely of AddField
                # operations; anything else must run for real.
                continue

            all_present = True
            for op in add_field_ops:
                table = f"{app_label}_{op.model_name}"
                if table not in existing_tables:
                    all_present = False
                    break
                with connection.cursor() as cursor:
                    columns = {c.name for c in connection.introspection.get_table_description(cursor, table)}
                if op.name not in columns:
                    all_present = False
                    break

            if all_present:
                self.stdout.write(f"Marking {app_label}.{name} as applied (columns already exist)")
                recorder.record_applied(app_label, name)
