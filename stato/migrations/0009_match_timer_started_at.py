# No-op: timer_started_at was reverted; 0010 drops the column if it exists anywhere.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stato', '0008_delete_oppositionstat'),
    ]

    operations = [
        # Intentionally empty - we no longer add timer_started_at; 0010 cleans up if it was ever added.
    ]
