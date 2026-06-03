from __future__ import annotations

from dataclasses import dataclass
from secrets import token_urlsafe

from django.contrib.auth import get_user_model
from django.core import signing

User = get_user_model()

GUEST_TOKEN_HEADER = "X-Guest-Token"
GUEST_TOKEN_QUERY = "guest_token"
_SIGNER = signing.TimestampSigner(salt="trip-planner-guest")


@dataclass(frozen=True)
class ActorContext:
    user: User | None
    guest_token: str | None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.user and getattr(self.user, "is_authenticated", False))


def create_guest_token() -> str:
    return _SIGNER.sign(token_urlsafe(24))


def parse_guest_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        _SIGNER.unsign(token, max_age=60 * 60 * 24 * 30)
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None
    return token


def get_guest_token_from_request(request) -> str | None:
    return parse_guest_token(
        request.headers.get(GUEST_TOKEN_HEADER)
        or request.query_params.get(GUEST_TOKEN_QUERY)
        or request.GET.get(GUEST_TOKEN_QUERY)
    )


def get_actor_context(request) -> ActorContext:
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    guest_token = None if user else get_guest_token_from_request(request)
    return ActorContext(user=user, guest_token=guest_token)
