import datetime as dt

from app.models import Compat, Game
from tests.factories import make_game, make_theme


def listing(html: str) -> str:
    """The main game list only (excludes best/random side blocks)."""
    return html.split('<div id="flashes">', 1)[1].split('id="flashes_random"', 1)[0]


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
    assert "Страница <b>" not in resp.text  # xxxflash paginator uses plain text
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
    assert "Тема: Квесты" in resp.text
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
