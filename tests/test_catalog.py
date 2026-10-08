import datetime as dt

from app.models import Compat, Game
from tests.factories import make_game, make_theme


def listing(html: str) -> str:
    """The main game list only (excludes best/random side blocks)."""
    return html.split('id="flashes"', 1)[1].split('id="flashes_random"', 1)[0]


async def test_index_lists_only_visible_games(client):
    visible = await make_game(name="Видимая игра")
    await make_game(name="Неактивная", active=False)
    await make_game(name="Будущая", published_at=dt.date.today() + dt.timedelta(days=3))
    await make_game(name="Низкий рейтинг", rate=-2)  # index requires rate > -2
    await make_game(name="Без файла", compat=Compat.MISSING)  # HIDE_COMPAT

    _, resp = await client.get("/")
    assert resp.status == 200
    main = listing(resp.text)
    assert f"/game/{visible.id}/" in main
    for hidden in ("Неактивная", "Будущая", "Низкий рейтинг", "Без файла"):
        assert hidden not in main


async def test_index_pagination(client):
    for i in range(20):  # GAMES_PER_PAGE=15
        await make_game(name=f"G{i:02d}")
    _, resp = await client.get("/?p=2")
    assert resp.status == 200
    assert "Страница 2 из 2." in resp.text
    _, resp = await client.get("/?p=999")  # out of range -> last page
    assert "Страница 2 из 2." in resp.text
    _, resp = await client.get("/?p=abc")
    assert resp.status == 404


async def test_best_orders_by_rate(client):
    low = await make_game(name="Low", rate=1)
    high = await make_game(name="High", rate=50)
    _, resp = await client.get("/best/")
    assert resp.status == 200
    assert resp.text.index(f'/game/{high.id}/" class="title"') < resp.text.index(
        f'/game/{low.id}/" class="title"'
    )


async def test_theme_page(client):
    theme = await make_theme("Квесты", slug="quest", game_count=1)
    game = await make_game(name="Квест игра", themes=[theme])
    await make_game(name="Другая игра")
    _, resp = await client.get("/theme/quest/")
    assert resp.status == 200
    assert "<h1>Квесты</h1>" in resp.text
    assert f'/game/{game.id}/" class="title"' in resp.text
    assert "Другая игра" not in listing(resp.text)
    _, resp = await client.get("/theme/unknown/")
    assert resp.status == 404


async def test_menu_shows_themes_with_games(client):
    await make_theme("Пустая", slug="empty", game_count=0)
    await make_theme("Полная", slug="full", game_count=3)
    _, resp = await client.get("/best/")
    assert "/theme/full/" in resp.text
    assert "/theme/empty/" not in resp.text


async def test_game_page_counts_views_only_with_referer(client):
    game = await make_game(rate=10, views=100)
    _, resp = await client.get(f"/game/{game.id}/")
    assert resp.status == 200
    assert 'class="game-player"' in resp.text
    assert "<object" not in resp.text
    await game.refresh_from_db()
    assert game.views == 100  # no Referer -> bot, not counted

    await client.get(f"/game/{game.id}/", headers={"Referer": "http://example.com/"})
    await game.refresh_from_db()
    assert game.views == 101
    assert game.xrate == 10 * 10000 / 100


async def test_inactive_game_is_404(client):
    game = await make_game(active=False)
    _, resp = await client.get(f"/game/{game.id}/")
    assert resp.status == 404


async def test_as3_game_shows_note(client):
    game = await make_game(compat=Compat.AS3)
    _, resp = await client.get(f"/game/{game.id}/")
    assert "Игра может работать некорректно" in resp.text


async def test_search(client):
    game = await make_game(name="Приключения русалки", description="морская история")
    await make_game(name="Совсем другое")
    _, resp = await client.get("/search/?q=русалка")
    assert resp.status == 302
    _, resp = await client.get(resp.headers["location"])
    assert resp.status == 200
    assert f'/game/{game.id}/" class="title"' in resp.text
    assert "Совсем другое" not in listing(resp.text)


async def test_search_empty_query_redirects_home(client):
    _, resp = await client.get("/search/?q=", follow_redirects=False)
    assert resp.status == 302
    assert resp.headers["location"] == "/"


async def test_get_comments_fragment(client):
    game = await make_game()
    _, resp = await client.get(f"/get_comments/{game.id}/1/")
    assert resp.status == 200
    assert 'id="comments_list"' in resp.text


async def test_media_parts_served_as_swf(client, media_root):
    (media_root / "parts").mkdir(exist_ok=True)
    (media_root / "parts" / "tah-game").write_bytes(b"CWS\x07fake")
    _, resp = await client.get("/media/parts/tah-game")
    assert resp.status == 200
    assert resp.headers["content-type"] == "application/x-shockwave-flash"


async def test_flashsex_templates_render(database):
    """The second template set renders the same pages."""
    import dataclasses
    import secrets

    from app.config import settings
    from app.server import create_app

    flashsex = dataclasses.replace(settings, site="flashsex")
    app = create_app(flashsex, name=f"fs_{secrets.token_hex(3)}", init_orm=False)
    game = await make_game(name="Игра для flashsex")
    for url in ("/", "/best/", "/popular/", f"/game/{game.id}/", "/login/"):
        _, resp = await app.asgi_client.get(url)
        assert resp.status == 200, url
        assert "FlashSexRU" in resp.text or "flashsexru" in resp.text
    assert await Game.filter(id=game.id).exists()


async def test_xfg0_templates_render(database):
    """xfg0.com: its own Russian design over the same views; every page renders."""
    import dataclasses
    import secrets

    from app.config import BASE_DIR, settings
    from app.models import Comment
    from app.server import create_app
    from tests.factories import headers, make_user
    from tests.test_i18n import VIEW_TEMPLATES

    missing = [t for t in VIEW_TEMPLATES if not (BASE_DIR / "templates" / "xfg0" / t).is_file()]
    assert not missing
    xfg0 = dataclasses.replace(settings, site="xfg0")
    assert xfg0.static_dir == BASE_DIR / "static" / "xfg0"
    app = create_app(xfg0, name=f"xfg_{secrets.token_hex(3)}", init_orm=False)
    theme = await make_theme("Квесты", slug="xfg-quest")
    game = await make_game(name="Игра для xfg0", themes=[theme], rate=7, views=1234)
    user = await make_user()
    await Comment.create(game=game, user=user, text="Отличная игра", ip="10.0.0.1")
    for url in (
        "/", "/?p=2", "/best/", "/best2/", "/popular/", "/random/", "/theme/xfg-quest/",
        "/search/игра/", f"/game/{game.id}/", f"/get_comments/{game.id}/1/", "/login/",
    ):  # fmt: skip
        _, resp = await app.asgi_client.get(url, headers=headers(user))
        assert resp.status == 200, url
        if "<html" in resp.text:
            assert '<html lang="ru">' in resp.text and "logo-lcd" in resp.text, url
    _, resp = await app.asgi_client.get(f"/game/{game.id}/", headers=headers(user))
    assert 'id="mark1">7</span>' in resp.text  # vote() rewrites just the number
    assert "Отличная игра" in resp.text and 'action="/add-comment"' in resp.text
    _, resp = await app.asgi_client.get("/upload/", headers=headers(user))
    assert resp.status == 200 and "Загрузить игру" in resp.text
    _, resp = await app.asgi_client.get("/no-such-page/")
    assert resp.status == 404 and "Такой страницы нет" in resp.text


async def test_theme_counts_skip_hidden_games(database):
    from app.maintenance import update_theme_counts
    from app.models import Theme

    theme = await make_theme("Квесты", slug="quest2")
    await make_game(themes=[theme])
    await make_game(themes=[theme], compat=Compat.MISSING)  # HIDE_COMPAT
    await make_game(themes=[theme], active=False)
    await update_theme_counts()
    assert (await Theme.get(id=theme.id)).game_count == 1
