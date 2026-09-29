"""Email through the Resend HTTP API. Without RESEND_API_KEY messages are only logged."""

import logging

import httpx

from app.config import Settings

log = logging.getLogger("app.mail")
RESEND_URL = "https://api.resend.com/emails"


async def send_email(settings: Settings, to: list[str], subject: str, text: str) -> bool:
    if not to:
        return False
    if not settings.resend_api_key:
        log.warning("RESEND_API_KEY not set; email to %s not sent:\n%s\n%s", to, subject, text)
        return False
    payload = {"from": settings.email_from, "to": to, "subject": subject, "text": text}
    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(RESEND_URL, json=payload, headers=headers)
    except httpx.HTTPError:
        log.exception("resend request failed")
        return False
    if resp.status_code >= 300:
        log.error("resend error %s: %s", resp.status_code, resp.text[:500])
        return False
    return True


async def send_login_link(settings: Settings, email: str, link: str) -> bool:
    host = settings.site_url.split("://", 1)[-1]
    text = (
        f"Для входа на сайт {host} пройдите по ссылке:\n{link}\n\n"
        "Ссылка одноразовая и действует 24 часа.\n"
        "Если вы не запрашивали вход, просто проигнорируйте это письмо."
    )
    return await send_email(settings, [email], f"Вход на сайт {host}", text)


async def send_moderation_notice(settings: Settings, game_id: int, name: str) -> bool:
    link = f"{settings.site_url}/{settings.admin_prefix}/games/{game_id}/"
    text = f"Загружена новая игра «{name}».\nМодерация: {link}"
    return await send_email(settings, settings.admin_emails, "New flash game was uploaded", text)
