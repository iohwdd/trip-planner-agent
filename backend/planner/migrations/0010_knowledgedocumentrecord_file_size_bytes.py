from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0009_knowledgedocumentrecord_progress_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgedocumentrecord",
            name="file_size_bytes",
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]
