import datetime as dt
import re
from types import SimpleNamespace

from app.models import Compat, Game, LoginToken, Theme, User
from app.services.auth import consume_login_token, issue_login_token
from app.web import client_ip
from tests.factories import CSRF, headers, make_game, make_png, make_swf, make_theme, make_user


async def test_login_flow_creates_user_and_logs_in(client, caplog):
    caplog.set_level("WARNING", logger="app.auth")
    _, resp = await client.post(
        "/login/", data={"csrf_token": CSRF, "email": "New.User@Example.com"}, headers=headers()
    )
    assert resp.status == 200
    assert "выслана ссылка" in resp.text
    user = await User.get(email="new.user@example.com")
    assert user.username == "new.user"

    link = re.search(r"http://testserver(/auth/\d+/[\w-]+/)", caplog.text).group(1)
    _, resp = await client.get(link)
    assert "Добро пожаловать new.user" in resp.text
    assert "sid=" in resp.headers.get("set-cookie", "")

    # single use (drop the session cookie the first visit set)
    client.cookies.clear()
    _, resp = await client.get(link)
    assert "Ошибка входа" in resp.text


async def test_login_rejects_bad_email_and_csrf(client):
    _, resp = await client.post(
        "/login/", data={"csrf_token": CSRF, "email": "nope"}, headers=headers()
    )
    assert "правильный адрес" in resp.text
    _, resp = await client.post("/login/", data={"email": "a@b.cd"})
    assert resp.status == 403


async def test_existing_user_keeps_account(database):
    user = await make_user("legacy", email="legacy@example.com", score=42)
    same, token = await issue_login_token("legacy@example.com")
    assert same.id == user.id
    assert (await consume_login_token(user.id, token)).score == 42


async def test_expired_token(database):
    user, token = await issue_login_token("late@example.com")
    await LoginToken.filter(user_id=user.id).update(
        expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    )
    assert await consume_login_token(user.id, token) is None


async def test_username_collision_gets_suffix(database):
    await make_user("bob", email="bob@one.com")
    user, _ = await issue_login_token("bob@two.com")
    assert user.username.startswith("bob_")


def test_client_ip_ignores_forwarded_from_untrusted_peer():
    app = SimpleNamespace(
        ctx=SimpleNamespace(settings=SimpleNamespace(trusted_proxies=["10.0.0.1"]))
    )
    req = SimpleNamespace(
        app=app,
        conn_info=SimpleNamespace(client_ip="192.0.2.5"),
        ip="192.0.2.5",
        headers={"x-forwarded-for": "203.0.113.1"},
    )
    assert client_ip(req) == "192.0.2.5"
    req.conn_info.client_ip = "10.0.0.1"
    assert client_ip(req) == "203.0.113.1"


def _upload(client, user, swf: bytes, theme_ids, name="Новая игра", thumb=None):
    data = {"csrf_token": CSRF, "name": name, "description": "Описание", "theme": theme_ids}
    files = {
        "flashfile": ("game.swf", swf, "application/x-shockwave-flash"),
        "thumbfile": ("shot.png", thumb if thumb is not None else make_png(), "image/png"),
    }
    return client.post("/upload/", data=data, files=files, headers=headers(user))


async def test_upload_requires_login(client):
    _, resp = await client.get("/upload/")
    assert resp.status == 302
    assert resp.headers["location"] == "/login/"


async def test_upload_creates_pending_game(client, media_root):
    user = await make_user(score=0)
    theme = await make_theme("Квесты", slug="quest")
    swf = make_swf(800, 600, version=9, as3=True)
    _, resp = await _upload(client, user, swf, [str(theme.id)])
    assert resp.status == 200
    assert "отправлена на модерацию" in resp.text

    game = await Game.get(name="Новая игра").prefetch_related("themes")
    assert game.active is False
    assert game.user_id == user.id  # legacy forced "Anonymous"; we keep the uploader
    assert (game.width, game.height, game.is_as3, game.compat) == (800, 600, True, Compat.AS3)
    assert (media_root / game.swf_path).read_bytes() == swf
    assert (media_root / game.thumb_path).is_file()
    assert [t.id for t in game.themes] == [theme.id]
    await user.refresh_from_db()
    assert user.score == 10

    # same file again -> duplicate
    _, resp = await _upload(client, user, swf, [str(theme.id)], name="Копия")
    assert "Эта игра уже загружена" in resp.text
    assert not await Game.exists(name="Копия")


async def test_upload_rejects_non_swf_and_bad_image(client):
    user = await make_user()
    theme = await make_theme()
    _, resp = await _upload(client, user, b"GIF89a....", [str(theme.id)])
    assert "Неверный тип файла" in resp.text
    _, resp = await _upload(client, user, make_swf(salt=b"x"), [str(theme.id)], thumb=b"notimg")
    assert "Неверный формат изображения" in resp.text
    assert await Game.all().count() == 0


async def test_admin_is_staff_only(client):
    user = await make_user()
    _, resp = await client.get("/secret-admin/", headers=headers(user))
    assert resp.status == 403


async def test_admin_moderation(client):
    staff = await make_user("mod", is_staff=True)
    theme = await make_theme("Квесты", slug="quest")
    pending = await make_game(name="Ждёт модерации", active=False, themes=[theme])

    _, resp = await client.get("/secret-admin/games/?status=pending", headers=headers(staff))
    assert resp.status == 200
    assert "Ждёт модерации" in resp.text

    _, resp = await client.get(f"/secret-admin/games/{pending.id}/", headers=headers(staff))
    assert resp.status == 200
    assert 'class="game-player"' in resp.text

    _, resp = await client.post(
        f"/secret-admin/games/{pending.id}/approve",
        data={"csrf_token": CSRF},
        headers=headers(staff),
    )
    assert resp.status == 302
    await pending.refresh_from_db()
    assert pending.active is True
    assert (await Theme.get(id=theme.id)).game_count == 1


async def test_admin_edit_game(client):
    staff = await make_user("mod", is_staff=True)
    t1 = await make_theme("A", slug="a")
    t2 = await make_theme("B", slug="b")
    game = await make_game(name="Old", themes=[t1])
    _, resp = await client.post(
        f"/secret-admin/games/{game.id}/",
        data={
            "csrf_token": CSRF,
            "name": "New name",
            "description": "d",
            "published_at": "2020-01-02",
            "theme": [str(t2.id)],
            "active": "on",
        },
        headers=headers(staff),
    )
    assert resp.status == 200
    game = await Game.get(id=game.id).prefetch_related("themes")
    assert game.name == "New name"
    assert game.published_at == dt.date(2020, 1, 2)
    assert [t.slug for t in game.themes] == ["b"]
