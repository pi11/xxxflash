"""Periodic maintenance jobs (the old `update_games_count` cron)."""

from tortoise import connections

from app.config import settings

# Theme.game_count = number of visible games in the theme: active, published, and not hidden by
# HIDE_COMPAT ($1, a text[]), so the genre rail matches what the theme page lists.
UPDATE_THEME_COUNTS_SQL = """
UPDATE themes t SET game_count = coalesce(c.n, 0)
FROM themes t2
LEFT JOIN (
    SELECT gt.theme_id, count(*) AS n
    FROM game_themes gt JOIN games g ON g.id = gt.game_id
    WHERE g.active AND g.published_at <= current_date AND NOT (g.compat = ANY($1::text[]))
    GROUP BY gt.theme_id
) c ON c.theme_id = t2.id
WHERE t.id = t2.id
"""


async def update_theme_counts(hide_compat: list[str] | None = None) -> None:
    hide = settings.hide_compat if hide_compat is None else hide_compat
    await connections.get("default").execute_query(UPDATE_THEME_COUNTS_SQL, [list(hide)])
