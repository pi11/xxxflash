"""Magic-link login, logout, user panel fragment."""

import logging
import time
from collections import defaultdict, deque

from sanic import Blueprint, Request
from sanic.response import redirect

from app.services.auth import consume_login_token, issue_login_token, normalize_email
from app.services.mail import send_login_link
from app.templating import render
from app.web import client_ip, csrf_protect, login, logout

bp = Blueprint("auth")
log = logging.getLogger("app.auth")

# In-process rate limit for login emails: per IP and per address.
LOGIN_LIMIT = 5
LOGIN_WINDOW = 3600
_attempts: dict[str, deque] = defaultdict(deque)


def _rate_limited(*keys: str) -> bool:
    now = time.monotonic()
    limited = False
    for key in keys:
        q = _attempts[key]
        while q and now - q[0] > LOGIN_WINDOW:
            q.popleft()
        if len(q) >= LOGIN_LIMIT:
            limited = True
    if not limited:
        for key in keys:
            _attempts[key].append(now)
    return limited


@bp.route("/login/", methods=["GET", "POST"])
@csrf_protect
async def login_view(request: Request):
    settings = request.app.ctx.settings
    t = request.app.ctx.locale.msg
    error = ""
    sended = False
    email_value = ""
    if request.method == "POST":
        email_value = (request.form or {}).get("email", "")
        email = normalize_email(email_value)
        if email is None:
            error = t("bad_email")
        elif _rate_limited(f"ip:{client_ip(request)}", f"email:{email}"):
            error = t("too_many_logins")
        else:
            user, token = await issue_login_token(email)
            link = f"{settings.site_url}/auth/{user.id}/{token}/"
            if settings.debug or not settings.resend_api_key:
                log.warning("login link for %s: %s", email, link)
            await send_login_link(settings, email, link, request.app.ctx.locale)
            sended = True
    return await render(request, "user/login.html", sended=sended, error=error, email=email_value)


@bp.get("/auth/<user_id:int>/<token:str>/")
async def auth(request: Request, user_id: int, token: str):
    user = await consume_login_token(user_id, token)
    if user is not None:
        login(request, user)
    return await render(request, "user/auth.html")


@bp.get("/logout/")
async def logout_view(request: Request):
    logout(request)
    return redirect("/")


@bp.get("/get-user-panel/")
async def user_panel(request: Request):
    return await render(request, "user/panel.html", themes=[])
