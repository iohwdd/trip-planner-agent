from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="authcode",
            name="failed_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
