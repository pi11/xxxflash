"""User game upload; new games wait in the moderation queue (active=False)."""

from sanic import Blueprint, Request
from tortoise.expressions import F

from app.models import Compat, Game, Theme, User
from app.services.mail import send_moderation_notice
from app.services.rules import UPLOAD_SCORE
from app.services.swf import SwfError, is_swf, parse_header, sha512_hex
from app.services.uploads import UploadError, store_swf, store_thumbnail
from app.templating import render
from app.web import csrf_protect, login_required

bp = Blueprint("upload")

MAX_NAME = 150
MAX_DESCRIPTION = 2000


def _file(request: Request, name: str):
    files = request.files.getlist(name) if request.files else None
    return files[0] if files else None


@bp.route("/upload/", methods=["GET", "POST"])
@login_required
@csrf_protect
async def upload(request: Request):
    settings = request.app.ctx.settings
    _ = request.app.ctx.tr
    all_themes = await Theme.all().order_by("name")
    errors: dict[str, str] = {}
    values = {"name": "", "description": "", "themes": []}
    done = None

    if request.method == "POST":
        form = request.form or {}
        values["name"] = (form.get("name") or "").strip()
        values["description"] = (form.get("description") or "").strip()
        theme_ids = []
        for raw in form.getlist("theme") or []:
            if raw.isdigit():
                theme_ids.append(int(raw))
        values["themes"] = theme_ids
        swf = _file(request, "flashfile")
        thumb = _file(request, "thumbfile")

        if not values["name"] or len(values["name"]) > MAX_NAME:
            errors["name"] = _("Введите название (до %(n)s символов).") % {"n": MAX_NAME}
        if not values["description"] or len(values["description"]) > MAX_DESCRIPTION:
            errors["description"] = _("Введите описание (до %(n)s символов).") % {
                "n": MAX_DESCRIPTION
            }
        themes = [t for t in all_themes if t.id in theme_ids]
        if not themes:
            errors["theme"] = _("Выберите хотя бы одну тему.")

        info = None
        if swf is None or not swf.body:
            errors["flashfile"] = _("Выберите файл игры.")
        elif len(swf.body) > settings.max_upload_mb * 1024 * 1024:
            errors["flashfile"] = _("Файл больше %(n)s МБ.") % {"n": settings.max_upload_mb}
        elif not is_swf(swf.body):
            errors["flashfile"] = _("Неверный тип файла")
        else:
            try:
                info = parse_header(swf.body)
            except SwfError:
                errors["flashfile"] = _("Файл повреждён")
            else:
                if await Game.exists(sha512=sha512_hex(swf.body)):
                    errors["flashfile"] = _("Эта игра уже загружена")
        if thumb is None or not thumb.body:
            errors["thumbfile"] = _("Выберите скриншот.")

        if not errors:
            try:
                thumb_path = store_thumbnail(settings.media_root, thumb.body)
            except UploadError as exc:
                errors["thumbfile"] = _(str(exc))
            else:
                swf_path = store_swf(settings.media_root, swf.body)
                user = request.ctx.user
                game = await Game.create(
                    name=values["name"],
                    description=values["description"],
                    user_id=user.id,
                    swf_path=swf_path,
                    thumb_path=thumb_path,
                    filesize=len(swf.body),
                    active=False,
                    sha512=sha512_hex(swf.body),
                    swf_version=info.version,
                    is_as3=info.is_as3,
                    width=info.width,
                    height=info.height,
                    compat=Compat.AS3 if info.is_as3 else Compat.OK,
                )
                await game.themes.add(*themes)
                await User.filter(id=user.id).update(score=F("score") + UPLOAD_SCORE)
                await send_moderation_notice(settings, game.id, game.name)
                done = game
                values = {"name": "", "description": "", "themes": []}

    return await render(
        request,
        "upload-flash.html",
        all_themes=all_themes,
        errors=errors,
        values=values,
        done=done,
    )
