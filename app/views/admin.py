"""Small built-in admin at /<ADMIN_PREFIX>/ (staff only)."""

import datetime as dt

from sanic import Blueprint, Request
from sanic.exceptions import NotFound
from sanic.response import redirect
from tortoise.expressions import Q

from app.config import Settings
from app.maintenance import update_theme_counts
from app.models import Ban, BannedWord, Comment, Compat, Game, Theme
from app.services.paging import page_param, paginate
from app.services.uploads import UploadError, store_thumbnail
from app.templating import render
from app.web import csrf_protect, staff_required

PER_PAGE = 50


def create_blueprint(settings: Settings) -> Blueprint:
    prefix = f"/{settings.admin_prefix}"
    bp = Blueprint("admin", url_prefix=prefix)

    async def page(request: Request, template: str, **ctx):
        return await render(request, f"admin/{template}", themes=[], prefix=prefix, **ctx)

    @bp.get("/")
    @staff_required
    async def dashboard(request: Request):
        counts = {
            "pending": await Game.filter(active=False).count(),
            "active": await Game.filter(active=True).count(),
            "missing": await Game.filter(active=True, compat=Compat.MISSING).count(),
            "as3": await Game.filter(active=True, compat=Compat.AS3).count(),
            "comments": await Comment.all().count(),
            "bans": await Ban.all().count(),
        }
        return await page(request, "dashboard.html", counts=counts)

    # --- games ---------------------------------------------------------------

    @bp.get("/games/")
    @staff_required
    async def games(request: Request):
        status = request.args.get("status", "pending")
        q = request.args.get("q", "").strip()
        qs = Game.all()
        if status == "pending":
            qs = qs.filter(active=False)
        elif status == "active":
            qs = qs.filter(active=True)
        elif status in {c.value for c in Compat}:
            qs = qs.filter(compat=status)
        if q:
            qs = (
                qs.filter(Q(name__icontains=q) | Q(swf_path__icontains=q) | Q(id=int(q)))
                if q.isdigit()
                else qs.filter(Q(name__icontains=q) | Q(swf_path__icontains=q))
            )
        result = await paginate(qs.order_by("-id"), page_param(request), PER_PAGE)
        return await page(request, "games.html", games=result, current=status, q=q)

    async def _get_game(game_id: int) -> Game:
        game = await Game.get_or_none(id=game_id).prefetch_related("themes", "user")
        if game is None:
            raise NotFound("game")
        return game

    @bp.route("/games/<game_id:int>/", methods=["GET", "POST"])
    @staff_required
    @csrf_protect
    async def game_edit(request: Request, game_id: int):
        game = await _get_game(game_id)
        all_themes = await Theme.all().order_by("name")
        errors = {}
        saved = False
        if request.method == "POST":
            form = request.form or {}
            name = (form.get("name") or "").strip()
            if not name or len(name) > 150:
                errors["name"] = "1–150 символов"
            try:
                published = dt.date.fromisoformat(form.get("published_at", ""))
            except ValueError:
                errors["published_at"] = "YYYY-MM-DD"
            theme_ids = {int(v) for v in form.getlist("theme") or [] if v.isdigit()}
            thumb = (request.files.getlist("thumbfile") or [None])[0] if request.files else None
            if not errors and thumb is not None and thumb.body:
                try:
                    game.thumb_path = store_thumbnail(
                        request.app.ctx.settings.media_root, thumb.body
                    )
                except UploadError as exc:
                    errors["thumbfile"] = str(exc)
            if not errors:
                game.name = name
                game.description = (form.get("description") or "").strip()
                game.active = form.get("active") == "on"
                game.published_at = published
                await game.save()
                await game.themes.clear()
                chosen = [t for t in all_themes if t.id in theme_ids]
                if chosen:
                    await game.themes.add(*chosen)
                await update_theme_counts()
                saved = True
                game = await _get_game(game_id)
        return await page(
            request,
            "game_edit.html",
            g=game,
            all_themes=all_themes,
            game_theme_ids={t.id for t in game.themes},
            errors=errors,
            saved=saved,
        )

    @bp.post("/games/<game_id:int>/approve")
    @staff_required
    @csrf_protect
    async def game_approve(request: Request, game_id: int):
        await Game.filter(id=game_id).update(active=True, published_at=dt.date.today())
        await update_theme_counts()
        return redirect(f"{prefix}/games/?status=pending")

    @bp.post("/games/<game_id:int>/delete")
    @staff_required
    @csrf_protect
    async def game_delete(request: Request, game_id: int):
        game = await _get_game(game_id)
        await game.delete()
        await update_theme_counts()
        return redirect(f"{prefix}/games/")

    # --- themes --------------------------------------------------------------

    @bp.route("/themes/", methods=["GET", "POST"])
    @staff_required
    @csrf_protect
    async def themes(request: Request):
        error = ""
        if request.method == "POST":
            form = request.form or {}
            name = (form.get("name") or "").strip()
            slug = (form.get("slug") or "").strip()
            if not name or not slug:
                error = "name and slug are required"
            elif await Theme.exists(slug=slug):
                error = "slug already exists"
            else:
                await Theme.create(
                    name=name, slug=slug, sort_order=int(form.get("sort_order") or 0)
                )
                return redirect(f"{prefix}/themes/")
        return await page(request, "themes.html", all_themes=await Theme.all(), error=error)

    @bp.post("/themes/<theme_id:int>/")
    @staff_required
    @csrf_protect
    async def theme_edit(request: Request, theme_id: int):
        theme = await Theme.get_or_none(id=theme_id)
        if theme is None:
            raise NotFound("theme")
        form = request.form or {}
        if form.get("delete"):
            await theme.delete()
        else:
            theme.name = (form.get("name") or theme.name).strip()
            theme.slug = (form.get("slug") or theme.slug).strip()
            theme.sort_order = int(form.get("sort_order") or 0)
            theme.active = form.get("active") == "on"
            await theme.save()
        await update_theme_counts()
        return redirect(f"{prefix}/themes/")

    # --- comments ------------------------------------------------------------

    @bp.get("/comments/")
    @staff_required
    async def comments(request: Request):
        q = request.args.get("q", "").strip()
        qs = Comment.all().order_by("-id").prefetch_related("user", "game")
        if q:
            qs = qs.filter(Q(text__icontains=q) | Q(ip=q))
        result = await paginate(qs, page_param(request), PER_PAGE)
        return await page(request, "comments.html", comments=result, q=q)

    # --- bans & banned words -------------------------------------------------

    @bp.route("/bans/", methods=["GET", "POST"])
    @staff_required
    @csrf_protect
    async def bans(request: Request):
        if request.method == "POST":
            form = request.form or {}
            if ip := (form.get("remove") or "").strip():
                await Ban.filter(ip=ip).delete()
            elif ip := (form.get("ip") or "").strip():
                await Ban.get_or_create(ip=ip[:45])
            return redirect(f"{prefix}/bans/")
        return await page(request, "bans.html", bans=await Ban.all().order_by("-created_at"))

    @bp.route("/words/", methods=["GET", "POST"])
    @staff_required
    @csrf_protect
    async def words(request: Request):
        if request.method == "POST":
            form = request.form or {}
            if word := (form.get("remove") or "").strip():
                await BannedWord.filter(word=word).delete()
            elif word := (form.get("word") or "").strip().lower():
                await BannedWord.get_or_create(word=word[:100])
            return redirect(f"{prefix}/words/")
        return await page(request, "words.html", words=await BannedWord.all().order_by("word"))

    return bp
