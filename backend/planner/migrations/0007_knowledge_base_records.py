from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import planner.models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0006_assistant_conversations_and_plan_source_job"),
    ]

    operations = [
        migrations.CreateModel(
            name="KnowledgeBaseRecord",
            fields=[
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("knowledge_base_id", models.CharField(default=planner.models.generate_hex_id, editable=False, max_length=32, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("description", models.CharField(blank=True, max_length=400)),
                ("status", models.CharField(db_index=True, default="ready", max_length=16)),
                ("is_default", models.BooleanField(db_index=True, default=False)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_knowledge_bases", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "planner_knowledge_base",
                "indexes": [
                    models.Index(fields=["is_default", "status"], name="planner_kno_is_defa_11e9d3_idx"),
                    models.Index(fields=["slug"], name="planner_kno_slug_366aad_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="KnowledgeDocumentRecord",
            fields=[
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("document_id", models.CharField(default=planner.models.generate_hex_id, editable=False, max_length=32, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("file_name", models.CharField(max_length=255)),
                ("mime_type", models.CharField(blank=True, max_length=120)),
                ("source_type", models.CharField(default="upload", max_length=24)),
                ("bucket_name", models.CharField(max_length=120)),
                ("object_key", models.CharField(max_length=255, unique=True)),
                ("checksum", models.CharField(db_index=True, max_length=64)),
                ("status", models.CharField(db_index=True, default="pending", max_length=16)),
                ("chunk_count", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_knowledge_documents", to=settings.AUTH_USER_MODEL)),
                ("knowledge_base", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="document_records", to="planner.knowledgebaserecord")),
            ],
            options={
                "db_table": "planner_knowledge_document",
                "indexes": [
                    models.Index(fields=["knowledge_base", "-updated_at"], name="planner_kno_knowled_998f56_idx"),
                    models.Index(fields=["knowledge_base", "status"], name="planner_kno_knowled_f53103_idx"),
                ],
            },
        ),
    ]
