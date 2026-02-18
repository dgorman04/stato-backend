# Remove timer_started_at if it was ever added (safe no-op where column doesn't exist)

from django.db import migrations


def drop_timer_started_at(apps, schema_editor):
    schema_editor.execute(
        "ALTER TABLE stato_match DROP COLUMN IF EXISTS timer_started_at;"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('stato', '0009_match_timer_started_at'),
    ]

    operations = [
        migrations.RunPython(drop_timer_started_at, migrations.RunPython.noop),
    ]
