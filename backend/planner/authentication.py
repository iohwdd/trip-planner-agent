from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

from planner.services.auth_state_store import AuthStateStore

User = get_user_model()


class CacheTokenAuthentication(authentication.BaseAuthentication):
    def __init__(self) -> None:
        self.state_store = AuthStateStore()

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header:
            return None
        if header[0].lower() != b"bearer":
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("无效的认证令牌。")

        try:
            token = header[1].decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise exceptions.AuthenticationFailed("无效的认证令牌。") from exc

        user_id = self.state_store.get_user_id_for_access_token(token)
        if not user_id:
            raise exceptions.AuthenticationFailed("认证已过期，请重新登录。")

        user = User.objects.filter(pk=user_id).first()
        if user is None:
            raise exceptions.AuthenticationFailed("登录用户不存在。")
        return user, token
