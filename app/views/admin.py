"""Small built-in admin at /<ADMIN_PREFIX>/ (staff only)."""

import datetime as dt
from urllib.parse import quote

from sanic import Blueprint, Request
from sanic.exceptions import NotFound
from sanic.response import redirect
from tortoise.expressions import Q

from app.config import Settings
from app.i18n import LANGUAGES
from app.maintenance import update_theme_counts
from app.models import (
    Ban,
    BannedWord,
    Comment,
    Compat,
    Game,
    GameTranslation,
    Theme,
    ThemeTranslation,
    TranslationStatus,
)
from app.services.paging import page_param, paginate
from app.services.translate import source_hash
from app.services.uploads import UploadError, store_thumbnail
from app.templating import render
from app.web import csrf_protect, staff_required

PER_PAGE = 50
TARGET_LANGUAGES = [lang for lang in LANGUAGES if lang != "ru"]


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
        message = request.args.get("msg", "")
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
                await _save_translations(game, form)
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
            message=message,
            translations=await _translations(game),
            languages=TARGET_LANGUAGES,
        )

    async def _translations(game: Game) -> dict[str, GameTranslation]:
        rows = await GameTranslation.filter(game_id=game.id, language__in=TARGET_LANGUAGES)
        current = source_hash(game.name, game.description)
        for row in rows:
            row.outdated = row.status != TranslationStatus.EDITED and row.source_hash != current
        return {row.language: row for row in rows}

    async def _save_translations(game: Game, form) -> None:
        """Hand-edited translations are marked `edited`; machine runs never overwrite them."""
        existing = await _translations(game)
        for lang in TARGET_LANGUAGES:
            name = (form.get(f"tr_{lang}_name") or "").strip()
            description = (form.get(f"tr_{lang}_description") or "").strip()
            row = existing.get(lang)
            if row is None and not name:
                continue
            if row is not None and (name, description) == (row.name, row.description):
                continue
            await GameTranslation.update_or_create(
                game_id=game.id,
                language=lang,
                defaults={
                    "name": name[:300],
                    "description": description,
                    "status": TranslationStatus.EDITED,
                    "error": None,
                    "source_hash": source_hash(game.name, game.description),
                },
            )

    @bp.post("/games/<game_id:int>/translate")
    @staff_required
    @csrf_protect
    async def game_translate(request: Request, game_id: int):
        from app.translate_job import find_candidates, make_translator, translate_game

        lang = (request.form or {}).get("lang", "en")
        if lang not in TARGET_LANGUAGES:
            raise NotFound("language")
        try:
            translator = make_translator(request.app.ctx.settings)
        except SystemExit as exc:
            return redirect(f"{prefix}/games/{game_id}/?msg={quote(str(exc))}")
        # An explicit request overrides even a hand-edited translation.
        await GameTranslation.filter(game_id=game_id, language=lang).delete()
        [cand] = await find_candidates(lang, ids=[game_id])
        status = await translate_game(translator, cand, lang)
        return redirect(f"{prefix}/games/{game_id}/?msg={quote(f'{lang}: {status.value}')}")

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

    async def save_theme_names(theme: Theme, form) -> None:
        """Genre names for the other-language sites; an empty field hides the genre there."""
        for lang in TARGET_LANGUAGES:
            name = (form.get(f"name_{lang}") or "").strip()[:250]
            if name:
                await ThemeTranslation.update_or_create(
                    theme=theme, language=lang, defaults={"name": name}
                )
            else:
                await ThemeTranslation.filter(theme=theme, language=lang).delete()

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
                theme = await Theme.create(
                    name=name, slug=slug, sort_order=int(form.get("sort_order") or 0)
                )
                await save_theme_names(theme, form)
                return redirect(f"{prefix}/themes/")
        names: dict[int, dict[str, str]] = {}
        for row in await ThemeTranslation.filter(language__in=TARGET_LANGUAGES):
            names.setdefault(row.theme_id, {})[row.language] = row.name
        return await page(
            request,
            "themes.html",
            all_themes=await Theme.all(),
            names=names,
            languages=TARGET_LANGUAGES,
            error=error,
        )

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
            await save_theme_names(theme, form)
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
