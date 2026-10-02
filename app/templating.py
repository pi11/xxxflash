"""Jinja2 environment for the active SITE and the `render` helper."""

import datetime as dt
import hashlib

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from sanic import Request
from sanic.response import html

from app.config import BASE_DIR, Settings
from app.i18n import Locale
from app.services.rules import truncate_words


def _date(value, fmt: str = "%d.%m.%Y") -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        value = value.date()
    return value.strftime(fmt)


def create_env(settings: Settings) -> Environment:
    locale = Locale(settings.language)
    if not settings.template_dir.is_dir():
        raise ValueError(
            f"no templates for SITE={settings.site} SITE_LANGUAGE={settings.language}: "
            f"{settings.template_dir} is missing"
        )
    env = Environment(
        loader=ChoiceLoader(
            [
                FileSystemLoader(settings.template_dir),
                FileSystemLoader(BASE_DIR / "templates" / "_shared"),
            ]
        ),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    media_url = settings.media_url
    vendor_dir = BASE_DIR / "static" / "vendor"
    vendor_hashes: dict[str, str] = {}

    def static(path: str) -> str:
        return f"/static/{path.lstrip('/')}"

    def vendor(path: str) -> str:
        """Cache-bust by content hash: a CDN must never pair a stale ruffle.js with new wasm."""
        path = path.lstrip("/")
        if path not in vendor_hashes:
            try:
                data = (vendor_dir / path).read_bytes()
                vendor_hashes[path] = hashlib.sha1(data).hexdigest()[:10]
            except OSError:
                vendor_hashes[path] = ""
        v = vendor_hashes[path]
        return f"/vendor/{path}?v={v}" if v else f"/vendor/{path}"

    def media(path: str | None) -> str:
        return f"{media_url}{path}" if path else ""

    placeholder = static(
        "images/noimage.svg"
        if (settings.static_dir / "images" / "noimage.svg").is_file()
        else "images/noimage.jpg"
    )

    def thumb(game) -> str:
        """Game thumbnail, else first screenshot, else the site's placeholder."""
        if game.thumb_path:
            return media(game.thumb_path)
        shots = getattr(game, "screenshots", None)
        related = getattr(shots, "related_objects", None) if shots is not None else None
        if related:
            return media(related[0].image_path)
        return placeholder

    env.globals.update(
        settings=settings,
        static=static,
        vendor=vendor,
        media=media,
        thumb=thumb,
        now=lambda: dt.datetime.now(dt.UTC),
    )
    env.globals.update(plural=locale.plural, num=locale.number)
    # Genres keep their admin order, then alphabetical in the *displayed* language.
    env.filters["by_label"] = lambda themes: sorted(
        themes, key=lambda t: (-t.sort_order, t.title.casefold())
    )
    env.filters["truncatewords"] = truncate_words
    env.filters["date"] = _date
    return env


async def render(request: Request, template: str, status: int = 200, **context) -> object:
    from app.localize import localize
    from app.queries import menu_themes

    app = request.app
    context.setdefault("request", request)
    context.setdefault("user", request.ctx.user)
    context.setdefault("csrf_token", request.ctx.csrf_token)
    if "themes" not in context:
        context["themes"] = await menu_themes(app.ctx.settings)
    await localize(context.values(), app.ctx.settings.language)
    body = app.ctx.jinja.get_template(template).render(**context)
    return html(body, status=status)
