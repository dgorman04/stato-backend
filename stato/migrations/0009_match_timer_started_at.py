# Add timer_started_at so elapsed_seconds can be computed live when match is in progress

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stato', '0008_delete_oppositionstat'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='timer_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
