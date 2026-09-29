"""Listing pages: index, best, top, popular, random, theme, search."""

from urllib.parse import quote, unquote

from sanic import Blueprint, Request
from sanic.exceptions import NotFound
from sanic.response import redirect

from app.models import Game, Theme
from app.queries import (
    INDEX_ORDER,
    best_games,
    latest_comments,
    random_games,
    search_game_ids,
    top_users,
    visible_games,
)
from app.services.paging import Page, page_param, page_range, paginate
from app.services.rules import INDEX_MIN_RATE
from app.templating import render

bp = Blueprint("catalog")


def _cfg(request: Request):
    return request.app.ctx.settings


async def _page(request: Request, qs, per_page: int) -> Page:
    cfg = _cfg(request)
    return await paginate(
        qs.prefetch_related("screenshots"), page_param(request), per_page, cfg.page_links
    )


def _page_ctx(page: Page) -> dict:
    return {"flashes": page, "pages": page.page_range, "page_id": page.number}


@bp.get("/")
async def index(request: Request):
    cfg = _cfg(request)
    qs = visible_games().filter(rate__gt=INDEX_MIN_RATE).order_by(*INDEX_ORDER)
    page = await _page(request, qs, cfg.games_per_page)
    first_page = page.number == 1
    return await render(
        request,
        "index.html",
        index_page=True,
        first_page=first_page,
        top_profiles=await top_users(5) if first_page else [],
        best=await best_games(5),
        random2=await random_games(5),
        random=await random_games(7),
        comments=await latest_comments(5) if first_page and cfg.show_comments else [],
        **_page_ctx(page),
    )


async def _ranked(request: Request, order: tuple[str, ...], **flags):
    cfg = _cfg(request)
    page = await _page(request, visible_games().order_by(*order), cfg.best_games_per_page)
    return await render(
        request,
        "best_and_popular.html",
        base_url=request.path.rstrip("/"),
        random=await random_games(7),
        **flags,
        **_page_ctx(page),
    )


@bp.get("/best/")
async def best(request: Request):
    return await _ranked(request, ("-rate", "-id"), best=True)


@bp.get("/best2/")
async def best2(request: Request):
    return await _ranked(request, ("-xrate", "-id"), best=True, top=True)


@bp.get("/popular/")
async def popular(request: Request):
    return await _ranked(request, ("-views", "-id"), popular=True)


@bp.get("/random/")
async def random_page(request: Request):
    cfg = _cfg(request)
    games = await random_games(cfg.games_per_page)
    page = Page(number=1, num_pages=1, count=len(games), object_list=games, page_range=[1])
    return await render(
        request,
        "index.html",
        first_page=False,
        random_page=True,
        best=await best_games(5),
        random2=await random_games(5),
        random=await random_games(7),
        **_page_ctx(page),
    )


@bp.get("/theme/<slug:str>/")
async def theme(request: Request, slug: str):
    cfg = _cfg(request)
    theme = await Theme.get_or_none(slug=slug)
    if theme is None:
        raise NotFound("theme")
    qs = visible_games().filter(themes__id=theme.id).order_by("-xrate", "-id")
    page = await _page(request, qs, cfg.theme_games_per_page)
    return await render(
        request, "theme.html", theme=theme, random=await random_games(7), **_page_ctx(page)
    )


@bp.get("/search/")
async def search_form(request: Request):
    query = request.args.get("q", "").strip()[:300]
    if not query:
        return redirect("/")
    return redirect(f"/search/{quote(query, safe='')}")


@bp.get("/search/<query:path>")
async def search(request: Request, query: str):
    cfg = _cfg(request)
    query = unquote(query).strip()[:300]  # path params arrive percent-encoded
    if not query:
        # "/search/" also matches this route with an empty path: it is the ?q= form target
        return await search_form(request)
    ids = await search_game_ids(query)
    per_page = cfg.search_games_per_page
    num_pages = max(1, -(-len(ids) // per_page))
    number = page_param(request)
    if number < 1 or number > num_pages:
        number = num_pages
    chunk = ids[(number - 1) * per_page : number * per_page]
    by_id = {g.id: g for g in await Game.filter(id__in=chunk).prefetch_related("screenshots")}
    page = Page(
        number=number,
        num_pages=num_pages,
        count=len(ids),
        object_list=[by_id[i] for i in chunk if i in by_id],
        page_range=page_range(number, num_pages, cfg.page_links),
    )
    return await render(request, "search.html", query=query, **_page_ctx(page))
