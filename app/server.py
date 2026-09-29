"""Sanic application factory."""

import logging
import mimetypes

from sanic import Request, Sanic
from sanic.exceptions import Forbidden, NotFound, SanicException
from sanic.response import file, text
from tortoise.contrib.sanic import register_tortoise

from app.config import Settings, tortoise_config
from app.config import settings as default_settings
from app.templating import create_env
from app.web import load_request_state, save_request_state

log = logging.getLogger("app")

SWF_MIME = "application/x-shockwave-flash"
mimetypes.add_type(SWF_MIME, ".swf")
mimetypes.add_type("application/wasm", ".wasm")


def create_app(
    settings: Settings | None = None, name: str | None = None, init_orm: bool = True
) -> Sanic:
    settings = settings or default_settings
    app = Sanic(name or f"flash_{settings.site}")
    app.config.REQUEST_MAX_SIZE = (settings.max_upload_mb + 5) * 1024 * 1024
    app.config.FALLBACK_ERROR_FORMAT = "html"
    app.ctx.settings = settings
    app.ctx.jinja = create_env(settings)

    if init_orm:  # tests manage the ORM themselves
        register_tortoise(app, config=tortoise_config(settings))

        @app.before_server_start
        async def verify_schema(app):
            from app.db import check_search_path

            await check_search_path(settings)

    from app.views import admin, auth, catalog, game, upload

    app.blueprint(catalog.bp)
    app.blueprint(game.bp)
    app.blueprint(auth.bp)
    app.blueprint(upload.bp)
    app.blueprint(admin.create_blueprint(settings))

    _static_routes(app, settings)
    _middleware(app)
    _errors(app)
    return app


def _static_routes(app: Sanic, settings: Settings) -> None:
    media_prefix = settings.media_url.rstrip("/")
    parts_dir = settings.media_root / "parts"

    # Extensionless SWFs that loader games request as "parts/<name>" (see docs/ruffle.md).
    @app.get(f"{media_prefix}/parts/<name:str>", name="media_parts")
    async def media_parts(request: Request, name: str):
        path = (parts_dir / name).resolve()
        if path.parent != parts_dir.resolve() or not path.is_file():
            raise NotFound("not found")
        return await file(path, mime_type=SWF_MIME)

    @app.get("/robots.txt", name="robots")
    async def robots(request: Request):
        path = settings.static_dir / "robots.txt"
        if path.is_file():
            return await file(path, mime_type="text/plain")
        return text("User-agent: *\nDisallow:\n")

    app.static("/static", settings.static_dir, name="static")
    app.static("/vendor", settings.vendor_dir, name="vendor")
    app.static(media_prefix, settings.media_root, name="media")


def _middleware(app: Sanic) -> None:
    @app.on_request
    async def before(request: Request):
        if request.route and request.route.name.split(".")[-1] in ("static", "vendor", "media"):
            request.ctx.static = True
            return
        await load_request_state(request)

    @app.on_response
    async def after(request: Request, response):
        if getattr(request.ctx, "static", False) or not hasattr(request.ctx, "csrf_token"):
            return
        save_request_state(request, response)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer-when-downgrade")


def _errors(app: Sanic) -> None:
    from app.templating import render
    from app.web import ANONYMOUS

    async def _render_error(request: Request, template: str, status: int):
        if not hasattr(request.ctx, "user"):
            request.ctx.user = ANONYMOUS
            request.ctx.csrf_token = ""
        try:
            return await render(request, template, status=status, themes=[])
        except Exception:
            log.exception("error page rendering failed")
            return text(str(status), status=status)

    @app.exception(NotFound)
    async def not_found(request: Request, exc):
        return await _render_error(request, "404.html", 404)

    @app.exception(Forbidden)
    async def forbidden(request: Request, exc):
        return await _render_error(request, "403.html", 403)

    @app.exception(SanicException)
    async def sanic_error(request: Request, exc: SanicException):
        if exc.status_code >= 500:
            log.exception("server error", exc_info=exc)
            return await _render_error(request, "500.html", exc.status_code)
        return text(exc.message or str(exc.status_code), status=exc.status_code)

    @app.exception(Exception)
    async def server_error(request: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return await _render_error(request, "500.html", 500)
