"""copy-legacy against a miniature legacy schema shaped like the old Django tables."""

import dataclasses
import secrets

import asyncpg
import pytest

from app.config import settings
from app.copy_legacy import LegacyCopier
from app.models import Ban, BannedWord, Comment, Game, Screenshot, Theme, User, Vote

LEGACY_DDL = """
CREATE TABLE auth_user (id int PRIMARY KEY, username varchar, email varchar, is_staff bool,
    is_active bool, date_joined timestamptz, last_login timestamptz);
CREATE TABLE flash_profile (id int, user_id int, score int, avatar varchar);
CREATE TABLE flash_theme (id int PRIMARY KEY, name varchar, url varchar, active bool,
    publication_date date, count int, "order" int);
CREATE TABLE flash_flash (id int PRIMARY KEY, name varchar, description text, user_id int,
    flashfile varchar, thumbfile varchar, filesize varchar, rate int, views int, active bool,
    publication_date date, game_type int, datahash varchar, is_posted bool, height int,
    width int, xrate float8);
CREATE TABLE flash_flash_theme (id int, flash_id int, theme_id int);
CREATE TABLE flash_screenshot (id int, flash_id int, image varchar);
CREATE TABLE flash_cmark (id int, flash_id int, ip inet, mark int, publication_date date);
CREATE TABLE flash_comment (id int, flash_id int, user_id int, text text,
    publication_date date, ip varchar, ua varchar);
CREATE TABLE flash_ban (id int, ip inet, publication_date date);
CREATE TABLE flash_bannedword (id int, word varchar, publication_date timestamptz);

INSERT INTO auth_user VALUES
  (2, 'Anonymous', '', false, true, now(), null),
  (5, 'alice', 'Alice@Example.com', true, true, now(), now()),
  (9, 'alice2', 'alice@example.com', false, true, now(), null);
INSERT INTO flash_profile VALUES (1, 5, 77, 'avatars/missing.jpg'), (2, 9, 3, '');
INSERT INTO flash_theme VALUES (3, 'Квесты', 'quest', true, '2010-01-01', 0, 1);
INSERT INTO flash_flash VALUES
  (10, 'Игра', 'desc', 2, 'swf/a.swf', 'th/a.png', 'junk', 4, 100, true, '2011-01-01', 0,
   repeat('a', 128) || repeat('b', 128), false, 0, 0, 1.5),
  (11, 'Скачать', 'desc', 5, 'swf/b.swf', '', '0', -1, 5, true, '2011-01-01', 1,
   repeat('c', 256), false, 0, 0, 0);
INSERT INTO flash_flash_theme VALUES (1, 10, 3), (2, 10, 3);
INSERT INTO flash_screenshot VALUES (7, 10, 'screenshots/x.jpg');
INSERT INTO flash_cmark VALUES (1, 10, '10.0.0.1', 1, '2012-02-02'), (2, 10, '10.0.0.2', -1, null);
INSERT INTO flash_comment VALUES (4, 10, 9, 'Супер', '2013-03-03', '10.0.0.3', 'UA');
INSERT INTO flash_ban VALUES (1, '10.0.0.3', '2013-01-01'), (2, '10.0.0.3', '2014-01-01');
INSERT INTO flash_bannedword VALUES (1, ' Spam ', now()), (2, 'spam', now());
"""


@pytest.fixture
async def legacy_schema(database):
    schema = f"legacy_{secrets.token_hex(3)}"
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"; SET search_path = "{schema}";')
        await conn.execute(LEGACY_DDL)
        yield schema
    finally:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()


async def test_copy_legacy(legacy_schema, media_root):
    (media_root / "swf").mkdir(exist_ok=True)
    (media_root / "swf" / "a.swf").write_bytes(b"FWS" + b"\0" * 20)
    (media_root / "th").mkdir(exist_ok=True)
    (media_root / "th" / "a.png").write_bytes(b"png")

    # db_pgbouncer: no startup parameters, search_path via SET LOCAL (prod runs behind PgBouncer)
    cfg = dataclasses.replace(settings, legacy_schema=legacy_schema, db_pgbouncer=True)
    copier = LegacyCopier(cfg, media_root=media_root)
    copier.log = lambda *a: None
    report = await copier.run(truncate=True)

    assert report["users"] == (3, 3)
    assert report["votes"] == (2, 2)
    assert report["game_themes"] == (2, 1)  # legacy duplicates collapsed

    alice = await User.get(id=5)
    assert (alice.email, alice.is_staff, alice.score, alice.avatar) == (
        "alice@example.com",
        True,
        77,
        None,  # avatar file missing -> NULL
    )
    assert (await User.get(id=9)).email is None  # duplicate address
    assert (await User.get(id=2)).email is None

    game = await Game.get(id=10).prefetch_related("themes")
    assert game.sha512 == "a" * 128
    assert game.filesize == 23
    assert game.thumb_path == "th/a.png"
    assert [t.slug for t in game.themes] == ["quest"]
    assert (await Game.get(id=11)).active is False  # downloadable type dropped

    assert (await Theme.get(id=3)).game_count == 1
    assert await Screenshot.filter(game_id=10).count() == 1
    assert sorted(await Vote.all().values_list("value", flat=True)) == [-1, 1]
    assert (await Comment.get(id=4)).text == "Супер"
    assert await Ban.all().count() == 1
    assert await BannedWord.all().values_list("word", flat=True) == ["spam"]

    # new rows continue after the legacy ids
    new_user = await User.create(username="fresh")
    assert new_user.id == 10

    # running again without --truncate refuses to overwrite
    with pytest.raises(RuntimeError):
        await copier.run(truncate=False)


async def test_check_search_path_guard(database):
    from app.db import SearchPathError, check_search_path

    await check_search_path(settings, database)  # ORM connection resolves the test schema
    with pytest.raises(SearchPathError):
        await check_search_path(settings, "app_elsewhere")
