from __future__ import annotations

import logging
import math
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from planner.services.assistant_store import AssistantConversationStore
from planner.services.auth_state_store import AuthStateStore
from planner.services.chat_session_store import ChatSessionStore
from planner.services.event_store import event_store
from planner.models import PlanningJob

User = get_user_model()
logger = logging.getLogger(__name__)


class AuthRateLimitError(RuntimeError):
    pass


class AuthValidationError(RuntimeError):
    pass


class AuthDeliveryError(RuntimeError):
    pass


class AuthService:
    def __init__(self) -> None:
        self.assistant_store = AssistantConversationStore()
        self.chat_session_store = ChatSessionStore()
        self.state_store = AuthStateStore()

    def send_login_code(self, *, email: str, request_ip: str = "") -> dict:
        now = timezone.now()
        try:
            self.state_store.assert_can_send_code(
                email=email,
                request_ip=request_ip,
                now=now,
            )
        except RuntimeError as exc:
            raise AuthRateLimitError(str(exc)) from exc

        code = f"{random.randint(0, 999999):06d}"
        ttl_minutes = max(1, math.ceil(settings.TRIP_PLANNER_AUTH_CODE_TTL_SECONDS / 60))
        try:
            send_mail(
                subject="旅游规划 Agent 登录验证码",
                message=f"您的登录验证码是 {code}，有效期 {ttl_minutes} 分钟。",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception("Failed to deliver auth code email to %s", email)
            raise AuthDeliveryError("验证码发送失败，请稍后重试。") from exc
        self.state_store.store_login_code(
            email=email,
            code=code,
            request_ip=request_ip,
            now=now,
        )
        payload = {"message": "验证码已发送。"}
        if settings.DEBUG or settings.TRIP_PLANNER_EXPOSE_DEBUG_AUTH_CODE:
            payload["debug_code"] = code
        return payload

    def verify_login_code(
        self,
        *,
        email: str,
        code: str,
        guest_token: str | None = None,
    ) -> dict:
        now = timezone.now()
        auth_code = self.state_store.get_login_code_state(email)
        if auth_code is None:
            raise AuthValidationError("请先获取验证码。")
        if auth_code.status == AuthStateStore.CODE_STATUS_USED:
            raise AuthValidationError("验证码已使用，请重新获取。")
        if auth_code.status == AuthStateStore.CODE_STATUS_EXPIRED:
            raise AuthValidationError("验证码已过期，请重新获取。")
        if auth_code.expires_at <= now:
            auth_code.status = AuthStateStore.CODE_STATUS_EXPIRED
            self.state_store.save_login_code_state(auth_code)
            raise AuthValidationError("验证码已过期，请重新获取。")
        if auth_code.failed_attempts >= settings.TRIP_PLANNER_AUTH_CODE_MAX_VERIFY_ATTEMPTS:
            auth_code.status = AuthStateStore.CODE_STATUS_EXPIRED
            self.state_store.save_login_code_state(auth_code)
            raise AuthValidationError("验证码错误次数过多，请重新获取。")
        if auth_code.code != code:
            auth_code.failed_attempts += 1
            if (
                auth_code.failed_attempts
                >= settings.TRIP_PLANNER_AUTH_CODE_MAX_VERIFY_ATTEMPTS
            ):
                auth_code.status = AuthStateStore.CODE_STATUS_EXPIRED
            self.state_store.save_login_code_state(auth_code)
            if auth_code.status == AuthStateStore.CODE_STATUS_EXPIRED:
                raise AuthValidationError("验证码错误次数过多，请重新获取。")
            raise AuthValidationError("验证码错误。")

        user, _created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": f"user_{User.objects.count() + 1}_{random.randint(1000, 9999)}",
                "display_name": email.split("@", 1)[0],
            },
        )
        auth_code.status = AuthStateStore.CODE_STATUS_USED
        auth_code.used_at = now
        self.state_store.save_login_code_state(auth_code)

        if guest_token:
            migrated_assets = self._claim_guest_assets(guest_token, user)
            event_store.record(
                "guest_to_user_migration",
                owner_id=str(user.pk),
                guest_token=guest_token,
                payload={"email": email, **migrated_assets},
            )

        return self._issue_auth_payload(user)

    def login_with_password(
        self,
        *,
        email: str,
        password: str,
        guest_token: str | None = None,
    ) -> dict:
        user = User.objects.filter(email=email).first()
        if user is None:
            raise AuthValidationError("邮箱或密码错误。")
        if not user.has_usable_password():
            raise AuthValidationError("该账号尚未设置密码，请先使用验证码登录并设置密码。")
        if not user.check_password(password):
            raise AuthValidationError("邮箱或密码错误。")

        if guest_token:
            migrated_assets = self._claim_guest_assets(guest_token, user)
            event_store.record(
                "guest_to_user_migration",
                owner_id=str(user.pk),
                guest_token=guest_token,
                payload={"email": email, **migrated_assets, "login_method": "password"},
            )

        return self._issue_auth_payload(user)

    def set_password(
        self,
        *,
        user: User,
        new_password: str,
        current_password: str | None = None,
    ) -> dict:
        if len(new_password) < 8:
            raise AuthValidationError("密码长度至少需要 8 位。")
        if user.has_usable_password():
            if not current_password:
                raise AuthValidationError("请输入当前密码。")
            if not user.check_password(current_password):
                raise AuthValidationError("当前密码不正确。")

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return {"message": "密码已设置。"}

    def logout(self, *, refresh_token: str | None = None) -> None:
        if not refresh_token:
            return
        self.state_store.revoke_refresh_token(refresh_token)

    def _issue_auth_payload(self, user: User) -> dict:
        access_token, refresh_token = self.state_store.create_session_tokens(
            user_id=user.pk
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": str(user.pk),
                "email": user.email,
                "display_name": user.display_name,
                "has_password": user.has_usable_password(),
                "is_staff": bool(user.is_staff),
            },
        }

    def _claim_guest_assets(self, guest_token: str, user: User) -> dict[str, int]:
        now = timezone.now()
        planning_job_count = PlanningJob.objects.filter(owner__isnull=True).filter(
            Q(guest_token=guest_token) | Q(chat_turn__session__guest_token=guest_token)
        ).update(owner=user, updated_at=now)
        chat_session_count = self.chat_session_store.claim_guest_assets(guest_token, user)
        assistant_conversation_count = self.assistant_store.claim_guest_assets(
            guest_token, user
        )
        PlanningJob.objects.filter(
            guest_token=guest_token,
            owner=user,
        ).update(guest_token="")
        return {
            "planning_job_count": planning_job_count,
            "chat_session_count": chat_session_count,
            "assistant_conversation_count": assistant_conversation_count,
        }


auth_service = AuthService()
