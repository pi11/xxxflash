"""Reusable catalog queries (legacy filters and orderings)."""

import datetime as dt

from tortoise import connections
from tortoise.expressions import RawSQL
from tortoise.queryset import QuerySet

from app.config import settings
from app.models import Comment, Game, Theme, User

INDEX_ORDER = ("-published_at", "-rate", "-views", "-id")


def visible_games(hide_compat: list[str] | None = None) -> QuerySet[Game]:
    """Active, already published games, minus HIDE_COMPAT."""
    qs = Game.filter(active=True, published_at__lte=dt.date.today())
    hide = settings.hide_compat if hide_compat is None else hide_compat
    if hide:
        qs = qs.exclude(compat__in=hide)
    return qs


async def random_games(count: int) -> list[Game]:
    return (
        await visible_games()
        .annotate(_rnd=RawSQL("random()"))
        .order_by("_rnd")
        .limit(count)
        .prefetch_related("screenshots")
    )


async def best_games(count: int) -> list[Game]:
    return (
        await visible_games().order_by("-rate", "-id").limit(count).prefetch_related("screenshots")
    )


async def menu_themes() -> list[Theme]:
    return await Theme.filter(active=True, game_count__gt=0)


async def top_users(count: int = 5) -> list[User]:
    return await User.exclude(username="Anonymous").order_by("-score", "id").limit(count)


async def latest_comments(count: int = 5) -> list[Comment]:
    return await Comment.all().order_by("-id").limit(count).prefetch_related("user", "game")


async def search_game_ids(query: str, limit: int = 1000) -> list[int]:
    """Full-text (russian) + trigram/substring match on name, best matches first."""
    hide = settings.hide_compat
    conn = connections.get("default")
    sql = """
        SELECT id FROM (
            SELECT g.id,
                   ts_rank(g.search, plainto_tsquery('russian', $1)) AS rank,
                   similarity(g.name, $1) AS sim
            FROM games g
            WHERE g.active AND g.published_at <= current_date
              AND NOT (g.compat = ANY($2::text[]))
              AND (g.search @@ plainto_tsquery('russian', $1)
                   OR g.name % $1
                   OR g.name ILIKE '%' || $1 || '%')
        ) m
        ORDER BY rank DESC, sim DESC, id DESC
        LIMIT $3
    """
    rows = await conn.execute_query_dict(sql, [query, list(hide), limit])
    return [r["id"] for r in rows]
