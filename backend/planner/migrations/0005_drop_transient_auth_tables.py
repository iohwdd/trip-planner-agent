from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0004_delete_analyticsevent"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP TABLE IF EXISTS token_blacklist_blacklistedtoken;",
                "DROP TABLE IF EXISTS token_blacklist_outstandingtoken;",
                "DROP TABLE IF EXISTS django_session;",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
