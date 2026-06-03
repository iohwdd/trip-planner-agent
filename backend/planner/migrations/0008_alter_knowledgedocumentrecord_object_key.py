from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0007_knowledge_base_records"),
    ]

    operations = [
        migrations.AlterField(
            model_name="knowledgedocumentrecord",
            name="object_key",
            field=models.CharField(max_length=255, unique=True),
        ),
    ]
