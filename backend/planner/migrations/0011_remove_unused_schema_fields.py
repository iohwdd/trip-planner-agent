from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0010_knowledgedocumentrecord_file_size_bytes"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="assistantmessagerecord",
            name="metadata",
        ),
        migrations.RemoveField(
            model_name="knowledgedocumentrecord",
            name="bucket_name",
        ),
        migrations.RemoveField(
            model_name="knowledgedocumentrecord",
            name="checksum",
        ),
        migrations.RemoveField(
            model_name="knowledgedocumentrecord",
            name="created_by",
        ),
        migrations.RemoveField(
            model_name="knowledgedocumentrecord",
            name="source_type",
        ),
        migrations.RemoveField(
            model_name="knowledgebaserecord",
            name="created_by",
        ),
        migrations.RemoveField(
            model_name="user",
            name="phone",
        ),
    ]
