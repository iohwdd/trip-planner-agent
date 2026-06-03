from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

import planner.models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0005_drop_transient_auth_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantConversationRecord",
            fields=[
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("conversation_id", models.CharField(default=planner.models.generate_hex_id, editable=False, max_length=32, primary_key=True, serialize=False)),
                ("guest_token", models.CharField(blank=True, db_index=True, max_length=256, null=True)),
                ("title", models.CharField(default="未命名助手会话", max_length=120)),
                ("latest_summary", models.CharField(blank=True, max_length=400)),
                ("last_accessed_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="assistant_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "planner_assistant_conversation",
            },
        ),
        migrations.CreateModel(
            name="AssistantMessageRecord",
            fields=[
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("message_id", models.CharField(default=planner.models.generate_hex_id, editable=False, max_length=32, primary_key=True, serialize=False)),
                ("role", models.CharField(db_index=True, max_length=16)),
                ("content", models.TextField()),
                ("metadata", models.JSONField(default=dict)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="message_records", to="planner.assistantconversationrecord")),
            ],
            options={
                "db_table": "planner_assistant_message",
            },
        ),
        migrations.AddField(
            model_name="tripplanrecord",
            name="source_job",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trip_plans", to="planner.planningjob"),
        ),
        migrations.AddIndex(
            model_name="assistantconversationrecord",
            index=models.Index(fields=["owner", "-updated_at"], name="planner_ass_owner_i_10d650_idx"),
        ),
        migrations.AddIndex(
            model_name="assistantconversationrecord",
            index=models.Index(fields=["guest_token", "-updated_at"], name="planner_ass_guest_t_e5c9fb_idx"),
        ),
        migrations.AddIndex(
            model_name="assistantmessagerecord",
            index=models.Index(fields=["conversation", "created_at"], name="planner_ass_convers_14e741_idx"),
        ),
    ]
