"""Request plumbing: session cookie, CSRF, client IP, current user, auth decorators."""

import hmac
import ipaddress
import secrets
from functools import wraps

from itsdangerous import BadSignature, URLSafeTimedSerializer
from sanic import Request
from sanic.exceptions import Forbidden
from sanic.response import redirect

from app.models import User

SESSION_COOKIE = "sid"
CSRF_COOKIE = "csrftoken"
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRFToken"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


class AnonymousUser:
    id = None
    username = ""
    is_staff = False
    is_authenticated = False
    score = 0

    def __str__(self) -> str:
        return ""


ANONYMOUS = AnonymousUser()


def _serializer(request: Request) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(request.app.ctx.settings.secret_key, salt="session")


def client_ip(request: Request) -> str:
    """Peer IP; X-Forwarded-For is trusted only when the peer is a trusted proxy."""
    trusted = request.app.ctx.settings.trusted_proxies
    peer = request.conn_info.client_ip if request.conn_info else request.ip
    if peer not in trusted:
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
        if hop not in trusted:
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                break
    return peer


async def load_request_state(request: Request) -> None:
    request.ctx.user = ANONYMOUS
    request.ctx.new_session = None  # user id to write, 0 to clear
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        try:
            data = _serializer(request).loads(raw, max_age=SESSION_MAX_AGE)
        except BadSignature:
            data = None
        if data and data.get("uid"):
            user = await User.get_or_none(id=data["uid"], is_active=True)
            if user is not None:
                request.ctx.user = user
    token = request.cookies.get(CSRF_COOKIE)
    request.ctx.csrf_new = not token
    request.ctx.csrf_token = token or secrets.token_urlsafe(24)


def save_request_state(request: Request, response) -> None:
    secure = request.app.ctx.settings.site_url.startswith("https://")
    if getattr(request.ctx, "csrf_new", False):
        response.add_cookie(
            CSRF_COOKIE,
            request.ctx.csrf_token,
            max_age=60 * 60 * 24 * 365,
            samesite="Lax",
            httponly=False,
            secure=secure,
        )
    new_session = getattr(request.ctx, "new_session", None)
    if new_session:
        value = _serializer(request).dumps({"uid": new_session})
        response.add_cookie(
            SESSION_COOKIE,
            value,
            max_age=SESSION_MAX_AGE,
            samesite="Lax",
            httponly=True,
            secure=secure,
        )
    elif new_session == 0:
        response.delete_cookie(SESSION_COOKIE)


def login(request: Request, user: User) -> None:
    request.ctx.user = user
    request.ctx.new_session = user.id


def logout(request: Request) -> None:
    request.ctx.user = ANONYMOUS
    request.ctx.new_session = 0


def check_csrf(request: Request) -> None:
    sent = request.headers.get(CSRF_HEADER) or (request.form or {}).get(CSRF_FIELD, "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not cookie or not sent or not hmac.compare_digest(sent, cookie):
        raise Forbidden("CSRF check failed")


def csrf_protect(handler):
    @wraps(handler)
    async def wrapper(request, *args, **kwargs):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            check_csrf(request)
        return await handler(request, *args, **kwargs)

    return wrapper


def login_required(handler):
    @wraps(handler)
    async def wrapper(request, *args, **kwargs):
        if not request.ctx.user.is_authenticated:
            return redirect("/login/")
        return await handler(request, *args, **kwargs)

    return wrapper


def staff_required(handler):
    @wraps(handler)
    async def wrapper(request, *args, **kwargs):
        if not request.ctx.user.is_staff:
            raise Forbidden("staff only")
        return await handler(request, *args, **kwargs)

    return wrapper
