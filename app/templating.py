"""Jinja2 environment for the active SITE and the `render` helper."""

import datetime as dt

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from sanic import Request
from sanic.response import html

from app.config import BASE_DIR, Settings
from app.i18n import Translator
from app.services.rules import truncate_words

RUFFLE_VERSION_FILE = BASE_DIR / "static" / "vendor" / "ruffle" / "VERSION"


def _date(value, fmt: str = "%d.%m.%Y") -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        value = value.date()
    return value.strftime(fmt)


def create_env(settings: Settings) -> Environment:
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
    ruffle_version = RUFFLE_VERSION_FILE.read_text().strip() if RUFFLE_VERSION_FILE.exists() else ""

    def static(path: str) -> str:
        return f"/static/{path.lstrip('/')}"

    def vendor(path: str) -> str:
        suffix = f"?v={ruffle_version}" if path.startswith("ruffle/") else ""
        return f"/vendor/{path.lstrip('/')}{suffix}"

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
        ruffle_version=ruffle_version,
    )
    tr = Translator(settings.language)
    env.globals.update(_=tr.gettext, plural=tr.plural, num=tr.number, lang=tr.language)
    # Genres keep their admin order, then alphabetical in the *displayed* language.
    env.filters["by_label"] = lambda themes: sorted(
        themes, key=lambda t: (-t.sort_order, tr.gettext(t.name).casefold())
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
