import logging

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


def decode_token_unverified(token: str) -> dict:
    """Decode without verification to extract org_id for secret lookup."""
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        raise AuthError("Malformed token") from exc


def decode_token(token: str, secret: str) -> dict:
    """Decode and verify with the org's secret."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except ExpiredSignatureError as exc:
        raise AuthError("Token expired") from exc
    except InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc
