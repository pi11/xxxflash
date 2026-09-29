"""Magic-link login: users are identified by email, links are single-use and expire."""

import datetime as dt
import hashlib
import re
import secrets

from tortoise.transactions import in_transaction

from app.models import LoginToken, User

TOKEN_TTL = dt.timedelta(hours=24)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str | None:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        return None
    return email


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def create_user_for_email(email: str) -> User:
    """Legacy login_view: username = local part, with a random suffix on collision."""
    base = re.sub(r"[^\w.\-]", "", email.split("@", 1)[0].lower())[:120] or "user"
    username = base
    while await User.exists(username=username):
        username = f"{base}_{secrets.token_hex(2)}"
    return await User.create(username=username, email=email)


async def issue_login_token(email: str) -> tuple[User, str]:
    """Find or create the user for `email` and return a fresh one-time token."""
    user = await User.get_or_none(email=email)
    if user is None:
        user = await create_user_for_email(email)
    token = secrets.token_urlsafe(32)
    await LoginToken.create(token_hash=_hash(token), user=user, expires_at=_now() + TOKEN_TTL)
    return user, token


async def consume_login_token(user_id: int, token: str) -> User | None:
    """Mark the token used and return its active user, or None if invalid/expired/used."""
    async with in_transaction():
        row = (
            await LoginToken.filter(token_hash=_hash(token), user_id=user_id)
            .select_for_update()
            .first()
        )
        if row is None or row.used_at is not None or row.expires_at < _now():
            return None
        row.used_at = _now()
        await row.save(update_fields=["used_at"])
    user = await User.get_or_none(id=user_id, is_active=True)
    if user is not None:
        user.last_login = _now()
        await user.save(update_fields=["last_login"])
    return user
