from django.db import migrations, models
from django.db.models import F


def mark_existing_messages_read(apps, schema_editor):
    # Messages sent before read tracking existed shouldn't all show up as
    # unread the moment this ships.
    DirectMessage = apps.get_model('social', 'DirectMessage')
    DirectMessage.objects.filter(read_at__isnull=True).update(read_at=F('created_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('social', '0004_savedpost'),
    ]

    operations = [
        migrations.AddField(
            model_name='directmessage',
            name='read_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_messages_read, migrations.RunPython.noop),
    ]
