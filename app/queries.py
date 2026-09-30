"""Reusable catalog queries (legacy filters and orderings), aware of the site language.

On a non-Russian site only games with a published translation (machine or edited) are visible;
see docs/architecture.md "Languages".
"""

import datetime as dt

from tortoise import connections
from tortoise.expressions import RawSQL
from tortoise.queryset import QuerySet

from app.config import Settings
from app.models import Comment, Game, Theme, TranslationStatus, User

INDEX_ORDER = ("-published_at", "-rate", "-views", "-id")
PUBLISHED = [TranslationStatus.MACHINE.value, TranslationStatus.EDITED.value]


def visible_games(cfg: Settings) -> QuerySet[Game]:
    """Active, already published games, minus HIDE_COMPAT, translated for the site language."""
    qs = Game.filter(active=True, published_at__lte=dt.date.today())
    if cfg.hide_compat:
        qs = qs.exclude(compat__in=cfg.hide_compat)
    if cfg.language != "ru":
        qs = qs.filter(translations__language=cfg.language, translations__status__in=PUBLISHED)
    return qs


async def random_games(cfg: Settings, count: int) -> list[Game]:
    return (
        await visible_games(cfg)
        .annotate(_rnd=RawSQL("random()"))
        .order_by("_rnd")
        .limit(count)
        .prefetch_related("screenshots")
    )


async def best_games(cfg: Settings, count: int) -> list[Game]:
    return (
        await visible_games(cfg)
        .order_by("-rate", "-id")
        .limit(count)
        .prefetch_related("screenshots")
    )


# Per-language genre counts: Theme.game_count is maintained for the Russian site only.
_TRANSLATED_THEME_COUNTS = """
    SELECT gt.theme_id, count(*) AS n
    FROM game_themes gt
    JOIN games g ON g.id = gt.game_id
    JOIN game_translations tr ON tr.game_id = g.id AND tr.language = $1
                              AND tr.status = ANY($2::text[])
    WHERE g.active AND g.published_at <= current_date AND NOT (g.compat = ANY($3::text[]))
    GROUP BY gt.theme_id
"""


async def menu_themes(cfg: Settings) -> list[Theme]:
    if cfg.language == "ru":
        return await Theme.filter(active=True, game_count__gt=0)
    rows = await connections.get("default").execute_query_dict(
        _TRANSLATED_THEME_COUNTS, [cfg.language, PUBLISHED, list(cfg.hide_compat)]
    )
    counts = {r["theme_id"]: r["n"] for r in rows}
    themes = await Theme.filter(active=True, id__in=list(counts))
    for t in themes:
        t.game_count = counts[t.id]
    return themes


async def top_users(count: int = 5) -> list[User]:
    return await User.exclude(username="Anonymous").order_by("-score", "id").limit(count)


async def latest_comments(count: int = 5) -> list[Comment]:
    return await Comment.all().order_by("-id").limit(count).prefetch_related("user", "game")


_SEARCH_RU = """
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

_SEARCH_TRANSLATED = """
    SELECT id FROM (
        SELECT g.id,
               ts_rank(tr.search, plainto_tsquery('english', $1)) AS rank,
               similarity(tr.name, $1) AS sim
        FROM games g
        JOIN game_translations tr ON tr.game_id = g.id AND tr.language = $4
                                  AND tr.status = ANY($5::text[])
        WHERE g.active AND g.published_at <= current_date
          AND NOT (g.compat = ANY($2::text[]))
          AND (tr.search @@ plainto_tsquery('english', $1)
               OR tr.name % $1
               OR tr.name ILIKE '%' || $1 || '%')
    ) m
    ORDER BY rank DESC, sim DESC, id DESC
    LIMIT $3
"""


async def search_game_ids(cfg: Settings, query: str, limit: int = 1000) -> list[int]:
    """Full-text + trigram/substring match on the name in the site language, best first."""
    conn = connections.get("default")
    params = [query, list(cfg.hide_compat), limit]
    if cfg.language == "ru":
        rows = await conn.execute_query_dict(_SEARCH_RU, params)
    else:
        rows = await conn.execute_query_dict(_SEARCH_TRANSLATED, [*params, cfg.language, PUBLISHED])
    return [r["id"] for r in rows]
