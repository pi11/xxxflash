"""Periodic maintenance jobs (the old `update_games_count` cron)."""

from tortoise import connections

# Theme.game_count = number of visible, published games in the theme.
UPDATE_THEME_COUNTS_SQL = """
UPDATE themes t SET game_count = coalesce(c.n, 0)
FROM themes t2
LEFT JOIN (
    SELECT gt.theme_id, count(*) AS n
    FROM game_themes gt JOIN games g ON g.id = gt.game_id
    WHERE g.active AND g.published_at <= current_date
    GROUP BY gt.theme_id
) c ON c.theme_id = t2.id
WHERE t.id = t2.id
"""


async def update_theme_counts() -> None:
    await connections.get("default").execute_script(UPDATE_THEME_COUNTS_SQL)
