from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def generate_hex_id() -> str:
    return uuid4().hex


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("The given email must be set.")
        email = self.normalize_email(email)
        username = extra_fields.pop("username", "") or generate_hex_id()[:24]
        user = self.model(email=email, username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True

    def touch(self) -> None:
        self.updated_at = timezone.now()


class User(AbstractUser):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=120, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        db_table = "planner_user"

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = generate_hex_id()[:24]
        if not self.display_name and self.email:
            self.display_name = self.email.split("@", 1)[0]
        super().save(*args, **kwargs)


class ChatSessionRecord(TimestampedModel):
    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_WAITING = "waiting_for_clarification"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"

    session_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    guest_token = models.CharField(
        max_length=256, null=True, blank=True, db_index=True
    )
    title = models.CharField(max_length=120, default="未命名会话")
    status = models.CharField(max_length=48, default=STATUS_IDLE, db_index=True)
    confirmed_constraints = models.JSONField(default=dict)
    latest_result = models.JSONField(null=True, blank=True)
    active_turn_id = models.CharField(max_length=32, null=True, blank=True)
    latest_summary = models.CharField(max_length=400, blank=True)
    last_accessed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "planner_chat_session"
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
            models.Index(fields=["guest_token", "-updated_at"]),
        ]


class AssistantConversationRecord(TimestampedModel):
    conversation_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assistant_conversations",
    )
    guest_token = models.CharField(
        max_length=256, null=True, blank=True, db_index=True
    )
    title = models.CharField(max_length=120, default="未命名助手会话")
    latest_summary = models.CharField(max_length=400, blank=True)
    last_accessed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "planner_assistant_conversation"
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
            models.Index(fields=["guest_token", "-updated_at"]),
        ]


class AssistantMessageRecord(TimestampedModel):
    message_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    conversation = models.ForeignKey(
        AssistantConversationRecord,
        on_delete=models.CASCADE,
        related_name="message_records",
    )
    role = models.CharField(max_length=16, db_index=True)
    content = models.TextField()

    class Meta:
        db_table = "planner_assistant_message"
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]


class KnowledgeBaseRecord(TimestampedModel):
    STATUS_READY = "ready"
    STATUS_DISABLED = "disabled"

    knowledge_base_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=64, unique=True)
    description = models.CharField(max_length=400, blank=True)
    status = models.CharField(max_length=16, default=STATUS_READY, db_index=True)
    is_default = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "planner_knowledge_base"
        indexes = [
            models.Index(fields=["is_default", "status"]),
            models.Index(fields=["slug"]),
        ]


class KnowledgeDocumentRecord(TimestampedModel):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"

    document_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    knowledge_base = models.ForeignKey(
        KnowledgeBaseRecord,
        on_delete=models.CASCADE,
        related_name="document_records",
    )
    title = models.CharField(max_length=200)
    file_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    object_key = models.CharField(max_length=255, unique=True)
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, default=STATUS_PENDING, db_index=True)
    status_detail = models.CharField(max_length=160, blank=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "planner_knowledge_document"
        indexes = [
            models.Index(fields=["knowledge_base", "-updated_at"]),
            models.Index(fields=["knowledge_base", "status"]),
        ]


class ChatTurnRecord(TimestampedModel):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    INPUT_CHAT = "chat"
    INPUT_FORM = "form"

    turn_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    session = models.ForeignKey(
        ChatSessionRecord,
        on_delete=models.CASCADE,
        related_name="turn_records",
    )
    status = models.CharField(max_length=16, default=STATUS_QUEUED, db_index=True)
    input_mode = models.CharField(max_length=16, default=INPUT_CHAT)
    user_message = models.JSONField()
    request_payload = models.JSONField(null=True, blank=True)
    confirmed_constraints = models.JSONField(default=dict)
    steps = models.JSONField(default=list)
    result_payload = models.JSONField(null=True, blank=True)
    assistant_message = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        db_table = "planner_chat_turn"
        indexes = [
            models.Index(fields=["session", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class TripPlanRecord(TimestampedModel):
    STATUS_DRAFT = "draft"
    STATUS_FINAL = "final"

    plan_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trip_plans",
    )
    source_session = models.ForeignKey(
        ChatSessionRecord,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trip_plans",
    )
    source_turn = models.ForeignKey(
        ChatTurnRecord,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trip_plans",
    )
    source_job = models.ForeignKey(
        "PlanningJob",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trip_plans",
    )
    title = models.CharField(max_length=160, default="未命名方案")
    status = models.CharField(max_length=16, default=STATUS_DRAFT, db_index=True)
    version = models.PositiveIntegerField(default=1)
    constraints_snapshot = models.JSONField(default=dict)
    result_snapshot = models.JSONField(default=dict)

    class Meta:
        db_table = "planner_trip_plan"
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
            models.Index(fields=["source_session", "version"]),
        ]


class PlanningJob(TimestampedModel):
    TYPE_PLAN_RUN = "plan_run"
    TYPE_CHAT_TURN = "chat_turn"

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"

    job_id = models.CharField(
        primary_key=True, max_length=32, default=generate_hex_id, editable=False
    )
    job_type = models.CharField(max_length=24, db_index=True)
    status = models.CharField(max_length=16, default=STATUS_QUEUED, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="planning_jobs",
    )
    guest_token = models.CharField(max_length=256, blank=True, db_index=True)
    chat_turn = models.OneToOneField(
        ChatTurnRecord,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="planning_job",
    )
    request_payload = models.JSONField(null=True, blank=True)
    steps = models.JSONField(default=list)
    result_payload = models.JSONField(null=True, blank=True)
    timeout_seconds = models.PositiveIntegerField(default=90)
    attempts = models.PositiveIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    metrics = models.JSONField(default=dict)

    class Meta:
        db_table = "planner_planning_job"
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]
