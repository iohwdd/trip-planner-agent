from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from secrets import token_urlsafe
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


@dataclass
class AuthCodeState:
    email: str
    code: str
    request_ip: str
    status: str
    failed_attempts: int
    sent_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "code": self.code,
            "request_ip": self.request_ip,
            "status": self.status,
            "failed_attempts": self.failed_attempts,
            "sent_at": self.sent_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "used_at": self.used_at.isoformat() if self.used_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthCodeState":
        return cls(
            email=data["email"],
            code=data["code"],
            request_ip=data.get("request_ip", ""),
            status=data.get("status", "sent"),
            failed_attempts=int(data.get("failed_attempts", 0)),
            sent_at=datetime.fromisoformat(data["sent_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            used_at=(
                datetime.fromisoformat(data["used_at"])
                if data.get("used_at")
                else None
            ),
        )


class AuthStateStore:
    CODE_STATUS_SENT = "sent"
    CODE_STATUS_USED = "used"
    CODE_STATUS_EXPIRED = "expired"

    CODE_TTL_BUFFER_SECONDS = 3600

    @staticmethod
    def _code_key(email: str) -> str:
        return f"auth:code:login:{email.lower()}"

    @staticmethod
    def _email_log_key(email: str) -> str:
        return f"auth:send-log:email:{email.lower()}"

    @staticmethod
    def _ip_log_key(request_ip: str) -> str:
        return f"auth:send-log:ip:{request_ip}"

    @staticmethod
    def _access_key(token: str) -> str:
        return f"auth:access:{token}"

    @staticmethod
    def _refresh_key(token: str) -> str:
        return f"auth:refresh:{token}"

    @staticmethod
    def _prune_timestamps(
        key: str,
        *,
        now,
        window_seconds: int,
    ) -> list[float]:
        raw_values = cache.get(key, [])
        now_ts = now.timestamp()
        values = [
            float(value)
            for value in raw_values
            if now_ts - float(value) < window_seconds
        ]
        cache.set(key, values, window_seconds)
        return values

    def assert_can_send_code(self, *, email: str, request_ip: str, now) -> None:
        interval_seconds = settings.TRIP_PLANNER_AUTH_CODE_INTERVAL_SECONDS
        window_seconds = settings.TRIP_PLANNER_AUTH_CODE_WINDOW_SECONDS

        email_values = self._prune_timestamps(
            self._email_log_key(email),
            now=now,
            window_seconds=window_seconds,
        )
        if email_values and now.timestamp() - email_values[-1] < interval_seconds:
            raise RuntimeError("验证码发送过于频繁，请稍后再试。")
        if len(email_values) >= settings.TRIP_PLANNER_AUTH_CODE_MAX_PER_WINDOW:
            raise RuntimeError("验证码发送次数已达上限，请稍后再试。")

        if request_ip:
            ip_values = self._prune_timestamps(
                self._ip_log_key(request_ip),
                now=now,
                window_seconds=window_seconds,
            )
            if len(ip_values) >= settings.TRIP_PLANNER_AUTH_CODE_MAX_PER_IP_WINDOW:
                raise RuntimeError("当前请求来源发送次数已达上限，请稍后再试。")

    def store_login_code(
        self,
        *,
        email: str,
        code: str,
        request_ip: str,
        now,
    ) -> AuthCodeState:
        state = AuthCodeState(
            email=email,
            code=code,
            request_ip=request_ip,
            status=self.CODE_STATUS_SENT,
            failed_attempts=0,
            sent_at=now,
            expires_at=now
            + timedelta(seconds=settings.TRIP_PLANNER_AUTH_CODE_TTL_SECONDS),
        )
        ttl_seconds = (
            settings.TRIP_PLANNER_AUTH_CODE_TTL_SECONDS + self.CODE_TTL_BUFFER_SECONDS
        )
        cache.set(self._code_key(email), state.as_dict(), ttl_seconds)

        window_seconds = settings.TRIP_PLANNER_AUTH_CODE_WINDOW_SECONDS
        email_values = self._prune_timestamps(
            self._email_log_key(email),
            now=now,
            window_seconds=window_seconds,
        )
        cache.set(
            self._email_log_key(email),
            [*email_values, now.timestamp()],
            window_seconds,
        )
        if request_ip:
            ip_values = self._prune_timestamps(
                self._ip_log_key(request_ip),
                now=now,
                window_seconds=window_seconds,
            )
            cache.set(
                self._ip_log_key(request_ip),
                [*ip_values, now.timestamp()],
                window_seconds,
            )
        return state

    def get_login_code_state(self, email: str) -> AuthCodeState | None:
        payload = cache.get(self._code_key(email))
        if not payload:
            return None
        return AuthCodeState.from_dict(payload)

    def save_login_code_state(self, state: AuthCodeState) -> None:
        ttl_seconds = max(
            1,
            int((state.expires_at - timezone.now()).total_seconds())
            + self.CODE_TTL_BUFFER_SECONDS,
        )
        cache.set(self._code_key(state.email), state.as_dict(), ttl_seconds)

    def create_session_tokens(self, *, user_id: Any) -> tuple[str, str]:
        access_token = token_urlsafe(32)
        refresh_token = token_urlsafe(48)
        access_ttl = int(settings.SIMPLE_TOKEN["ACCESS_TOKEN_LIFETIME"].total_seconds())
        refresh_ttl = int(
            settings.SIMPLE_TOKEN["REFRESH_TOKEN_LIFETIME"].total_seconds()
        )
        cache.set(
            self._access_key(access_token),
            {"user_id": str(user_id), "refresh_token": refresh_token},
            access_ttl,
        )
        cache.set(
            self._refresh_key(refresh_token),
            {"user_id": str(user_id), "access_token": access_token},
            refresh_ttl,
        )
        return access_token, refresh_token

    def get_user_id_for_access_token(self, token: str) -> str | None:
        payload = cache.get(self._access_key(token))
        if not payload:
            return None
        return payload.get("user_id")

    def revoke_refresh_token(self, token: str) -> None:
        payload = cache.get(self._refresh_key(token))
        if payload and payload.get("access_token"):
            cache.delete(self._access_key(payload["access_token"]))
        cache.delete(self._refresh_key(token))
