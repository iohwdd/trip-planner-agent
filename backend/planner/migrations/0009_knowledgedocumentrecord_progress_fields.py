from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0008_alter_knowledgedocumentrecord_object_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgedocumentrecord",
            name="progress_percent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="knowledgedocumentrecord",
            name="status_detail",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
