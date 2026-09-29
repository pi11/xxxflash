"""Game page, comment pages, voting, comment actions."""

from sanic import Blueprint, Request
from sanic.exceptions import Forbidden, NotFound
from sanic.response import json, redirect
from tortoise.expressions import F
from tortoise.transactions import in_transaction

from app.models import Ban, BannedWord, Comment, Game, User, Vote
from app.queries import random_games, visible_games
from app.services.paging import paginate
from app.services.rules import (
    ALREADY_VOTED,
    COMMENT_SCORE,
    DELETE_COMMENT_PENALTY,
    VOTE_SCORE,
    comment_rejected,
    compute_xrate,
    should_auto_hide,
    vote_value,
)
from app.templating import render
from app.web import client_ip, csrf_protect, login_required, staff_required

bp = Blueprint("game")

MAX_COMMENT = 1000


async def _comments_page(request: Request, game: Game, number: int):
    cfg = request.app.ctx.settings
    qs = Comment.filter(game_id=game.id).order_by("-id").prefetch_related("user")
    return await paginate(qs, number, cfg.comments_per_page, cfg.page_links)


@bp.get("/game/<game_id:int>/")
async def game_page(request: Request, game_id: int):
    game = await visible_games().filter(id=game_id).prefetch_related("user", "themes").first()
    if game is None:
        raise NotFound("game")
    views = game.views
    # Legacy: requests without a Referer are treated as bots and not counted.
    if request.headers.get("referer"):
        xrate = compute_xrate(game.rate, views)
        await Game.filter(id=game.id).update(views=F("views") + 1, xrate=xrate)
    comments = await _comments_page(request, game, 1)
    return await render(
        request,
        "game.html",
        g=game,
        gt=list(game.themes),
        views=views,
        mark=game.rate,
        comments=comments,
        random=await random_games(7),
    )


@bp.get("/get_comments/<game_id:int>/<page_id:int>/")
async def get_comments(request: Request, game_id: int, page_id: int):
    game = await Game.get_or_none(id=game_id)
    if game is None:
        raise NotFound("game")
    comments = await _comments_page(request, game, page_id)
    return await render(request, "comments_list.html", g=game, comments=comments, themes=[])


@bp.post("/mark/")
@csrf_protect
async def mark(request: Request):
    form = request.form or {}
    try:
        game_id = int(form.get("pk", ""))
    except ValueError:
        raise NotFound("game") from None
    value = vote_value(form.get("vote", ""))
    if value is None:
        return json({"success": False}, status=400)
    user = request.ctx.user
    ip = client_ip(request)
    async with in_transaction():
        game = await Game.filter(id=game_id).select_for_update().first()
        if game is None:
            raise NotFound("game")
        if not user.is_staff and await Vote.exists(game_id=game.id, ip=ip):
            return json({"success": ALREADY_VOTED})
        await Vote.create(
            game_id=game.id, ip=ip, value=value, user_id=user.id if user.is_authenticated else None
        )
        game.rate += value
        fields = ["rate"]
        if should_auto_hide(game.rate):
            game.active = False
            fields.append("active")
        await game.save(update_fields=fields)
        if user.is_authenticated:
            await User.filter(id=user.id).update(score=F("score") + VOTE_SCORE)
        await User.filter(id=game.user_id).update(score=F("score") + value)  # uploader
    return json({"success": game.rate})


@bp.post("/add-comment")
@login_required
@csrf_protect
async def add_comment(request: Request):
    ip = client_ip(request)
    if await Ban.exists(ip=ip):
        raise Forbidden("banned")
    form = request.form or {}
    if form.get("email", ""):  # honeypot
        return redirect("/")
    text = (form.get("text", "") or "").strip()
    try:
        game_id = int(form.get("flash_id", ""))
    except ValueError:
        return redirect("/")
    if not text or len(text) > MAX_COMMENT:
        return redirect(f"/game/{game_id}/")
    words = await BannedWord.all().values_list("word", flat=True)
    if comment_rejected(text, list(words)):
        return redirect("/")
    if not await Game.exists(id=game_id):
        raise NotFound("game")
    user = request.ctx.user
    ua = (request.headers.get("user-agent", "No user agent") or "")[:250]
    await Comment.create(game_id=game_id, user_id=user.id, text=text, ip=ip, ua=ua)
    await User.filter(id=user.id).update(score=F("score") + COMMENT_SCORE)
    return redirect(f"/game/{game_id}/?new")


@bp.post("/del-comment/<comment_id:int>")
@staff_required
@csrf_protect
async def del_comment(request: Request, comment_id: int):
    comment = await Comment.get_or_none(id=comment_id)
    if comment is not None:
        await User.filter(id=comment.user_id).update(score=F("score") - DELETE_COMMENT_PENALTY)
        await comment.delete()
    return redirect(request.headers.get("referer") or "/")


@bp.post("/ban/<comment_id:int>/")
@staff_required
@csrf_protect
async def ban(request: Request, comment_id: int):
    comment = await Comment.get_or_none(id=comment_id)
    if comment is None:
        raise NotFound("comment")
    if comment.ip:
        await Ban.get_or_create(ip=comment.ip)
    return redirect("/?user_was_banned")
