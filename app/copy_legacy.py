"""Copy legacy Django tables (LEGACY_SCHEMA, default `public`) into the new schema (DB_SCHEMA).

Legacy rows are read by column name (column order differs between the old dumps) and written
with asyncpg COPY. IDs are preserved so /game/<id>/ URLs and foreign keys stay valid.
See docs/data-migration.md.
"""

import datetime as dt
from pathlib import Path

import asyncpg

from app.config import EXT_SCHEMA, Settings
from app.maintenance import UPDATE_THEME_COUNTS_SQL

# Target tables in dependency order (children last); truncated in reverse.
TABLES = [
    "users",
    "themes",
    "games",
    "game_themes",
    "screenshots",
    "votes",
    "comments",
    "bans",
    "banned_words",
]
SERIAL_TABLES = ["users", "themes", "games", "screenshots", "votes", "comments"]

LEGACY_COUNTS = {
    "users": "auth_user",
    "themes": "flash_theme",
    "games": "flash_flash",
    "game_themes": "flash_flash_theme",
    "screenshots": "flash_screenshot",
    "votes": "flash_cmark",
    "comments": "flash_comment",
    "bans": "flash_ban",
    "banned_words": "flash_bannedword",
}


def _midnight(d: dt.date | None) -> dt.datetime:
    """Legacy date -> UTC midnight; NULL dates (NOT NULL in the new schema) become 'now'."""
    if d is None:
        return dt.datetime.now(dt.UTC)
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.UTC)


class LegacyCopier:
    def __init__(self, settings: Settings, schema: str | None = None, media_root=None):
        self.settings = settings
        self.schema = schema or settings.db_schema
        self.legacy = settings.legacy_schema
        self.media_root = Path(media_root) if media_root else settings.media_root
        self.log = print

    def _file(self, rel: str | None) -> Path | None:
        if not rel:
            return None
        path = self.media_root / rel
        return path if path.is_file() else None

    async def run(self, truncate: bool = False) -> dict[str, tuple[int, int]]:
        conn = await asyncpg.connect(
            self.settings.database_url,
            server_settings={"search_path": f'"{self.schema}", {EXT_SCHEMA}'},
        )
        try:
            async with conn.transaction():
                await self._prepare(conn, truncate)
                await self._users(conn)
                await self._themes(conn)
                await self._games(conn)
                await self._game_themes(conn)
                await self._screenshots(conn)
                await self._votes(conn)
                await self._comments(conn)
                await self._bans(conn)
                await self._banned_words(conn)
                await self._reset_sequences(conn)
                await conn.execute(UPDATE_THEME_COUNTS_SQL)
            return await self._report(conn)
        finally:
            await conn.close()

    async def _prepare(self, conn, truncate: bool) -> None:
        if truncate:
            await conn.execute(f"TRUNCATE {', '.join(reversed(TABLES))}, login_tokens CASCADE")
            return
        for table in TABLES:
            if await conn.fetchval(f"SELECT EXISTS (SELECT 1 FROM {table})"):
                raise RuntimeError(f"{self.schema}.{table} is not empty; use --truncate")

    def _q(self, table: str) -> str:
        return f'"{self.legacy}".{table}'

    async def _copy(self, conn, table: str, columns: list[str], records: list[tuple]) -> None:
        await conn.copy_records_to_table(
            table, schema_name=self.schema, columns=columns, records=records
        )
        self.log(f"  {table}: {len(records)}")

    async def _users(self, conn) -> None:
        rows = await conn.fetch(
            f"""SELECT u.id, u.username, u.email, u.is_staff, u.is_active, u.date_joined,
                       u.last_login, coalesce(p.score, 0) AS score, p.avatar
                FROM {self._q("auth_user")} u
                LEFT JOIN {self._q("flash_profile")} p ON p.user_id = u.id
                ORDER BY u.id"""
        )
        seen: set[str] = set()
        records = []
        for r in rows:
            email = (r["email"] or "").strip().lower() or None
            if email in seen:
                email = None  # duplicate address: only the lowest id keeps it
            elif email:
                seen.add(email)
            avatar = r["avatar"] if self._file(r["avatar"]) else None
            records.append(
                (
                    r["id"],
                    r["username"][:150],
                    email,
                    r["is_staff"],
                    r["is_active"],
                    r["score"],
                    avatar,
                    r["date_joined"],
                    r["last_login"],
                )
            )
        await self._copy(
            conn,
            "users",
            [
                "id",
                "username",
                "email",
                "is_staff",
                "is_active",
                "score",
                "avatar",
                "created_at",
                "last_login",
            ],
            records,
        )

    async def _themes(self, conn) -> None:
        rows = await conn.fetch(
            f'SELECT id, name, url, active, "order" FROM {self._q("flash_theme")} ORDER BY id'
        )
        records = [(r["id"], r["name"], r["url"], r["active"], r["order"], 0) for r in rows]
        await self._copy(
            conn, "themes", ["id", "name", "slug", "active", "sort_order", "game_count"], records
        )

    async def _games(self, conn) -> None:
        rows = await conn.fetch(
            f"""SELECT id, name, description, user_id, flashfile, thumbfile, rate, views, xrate,
                       active, game_type, publication_date, datahash, width, height
                FROM {self._q("flash_flash")} ORDER BY id"""
        )
        records = []
        missing_swf = missing_thumb = 0
        for r in rows:
            swf = self._file(r["flashfile"])
            if swf is None:
                missing_swf += 1
            thumb = r["thumbfile"] if self._file(r["thumbfile"]) else None
            if r["thumbfile"] and thumb is None:
                missing_thumb += 1
            records.append(
                (
                    r["id"],
                    r["name"][:150],
                    r["description"] or "",
                    r["user_id"],
                    r["flashfile"],
                    thumb,
                    swf.stat().st_size if swf else 0,
                    r["rate"],
                    r["views"],
                    r["xrate"],
                    r["active"] and r["game_type"] == 0,  # downloadable games are dropped
                    r["publication_date"],
                    # legacy datahash = sha512(data) + sha512(b""); keep the real half
                    (r["datahash"] or "")[:128] or f"legacy-{r['id']}",
                    r["width"] or 0,
                    r["height"] or 0,
                    "unknown",
                    False,
                )
            )
        await self._copy(
            conn,
            "games",
            [
                "id",
                "name",
                "description",
                "user_id",
                "swf_path",
                "thumb_path",
                "filesize",
                "rate",
                "views",
                "xrate",
                "active",
                "published_at",
                "sha512",
                "width",
                "height",
                "compat",
                "is_as3",
            ],
            records,
        )
        self.log(f"    missing swf files: {missing_swf}, missing thumbnails: {missing_thumb}")

    async def _game_themes(self, conn) -> None:
        rows = await conn.fetch(
            f"SELECT DISTINCT flash_id, theme_id FROM {self._q('flash_flash_theme')}"
        )
        await self._copy(conn, "game_themes", ["game_id", "theme_id"], [tuple(r) for r in rows])

    async def _screenshots(self, conn) -> None:
        rows = await conn.fetch(
            f"SELECT id, flash_id, image FROM {self._q('flash_screenshot')} ORDER BY id"
        )
        await self._copy(
            conn, "screenshots", ["id", "game_id", "image_path"], [tuple(r) for r in rows]
        )

    async def _votes(self, conn) -> None:
        rows = await conn.fetch(
            f"""SELECT id, flash_id, host(ip) AS ip, sign(mark)::int AS value, publication_date
                FROM {self._q("flash_cmark")} WHERE mark <> 0 ORDER BY id"""
        )
        records = [
            (r["id"], r["flash_id"], r["ip"], r["value"], _midnight(r["publication_date"]))
            for r in rows
        ]
        await self._copy(conn, "votes", ["id", "game_id", "ip", "value", "created_at"], records)

    async def _comments(self, conn) -> None:
        rows = await conn.fetch(
            f"""SELECT id, flash_id, user_id, text, ip, ua, publication_date
                FROM {self._q("flash_comment")} ORDER BY id"""
        )
        records = [
            (
                r["id"],
                r["flash_id"],
                r["user_id"],
                r["text"],
                (r["ip"] or "")[:45] or None,
                (r["ua"] or "")[:250] or None,
                _midnight(r["publication_date"]),
            )
            for r in rows
        ]
        await self._copy(
            conn,
            "comments",
            ["id", "game_id", "user_id", "text", "ip", "ua", "created_at"],
            records,
        )

    async def _bans(self, conn) -> None:
        rows = await conn.fetch(
            f"""SELECT host(ip) AS ip, min(publication_date) AS d
                FROM {self._q("flash_ban")} GROUP BY host(ip)"""
        )
        await self._copy(
            conn, "bans", ["ip", "created_at"], [(r["ip"], _midnight(r["d"])) for r in rows]
        )

    async def _banned_words(self, conn) -> None:
        rows = await conn.fetch(
            f"""SELECT lower(trim(word)) AS word, min(publication_date) AS d
                FROM {self._q("flash_bannedword")}
                WHERE trim(word) <> '' GROUP BY lower(trim(word))"""
        )
        await self._copy(
            conn, "banned_words", ["word", "created_at"], [(r["word"], r["d"]) for r in rows]
        )

    async def _reset_sequences(self, conn) -> None:
        for table in SERIAL_TABLES:
            await conn.execute(
                f"""SELECT setval(pg_get_serial_sequence('"{self.schema}".{table}', 'id'),
                                  coalesce((SELECT max(id) FROM {table}), 0) + 1, false)"""
            )

    async def _report(self, conn) -> dict[str, tuple[int, int]]:
        report = {}
        for table, legacy in LEGACY_COUNTS.items():
            new = await conn.fetchval(f"SELECT count(*) FROM {table}")
            old = await conn.fetchval(f"SELECT count(*) FROM {self._q(legacy)}")
            report[table] = (old, new)
        return report
