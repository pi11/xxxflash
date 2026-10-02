import dataclasses
import re
import secrets

import pytest

from app.config import BASE_DIR, settings
from app.i18n import MESSAGES, Locale
from app.models import Comment, Theme, ThemeTranslation, TranslationStatus
from tests.factories import CSRF, headers, make_game, make_theme, make_user, translate

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
TEMPLATES = BASE_DIR / "templates"


def _names(directory):
    return {p.relative_to(directory).as_posix() for p in directory.rglob("*.html")}


# Templates the views render; each language set must have them (it may name partials freely).
VIEW_TEMPLATES = (
    "index.html", "best_and_popular.html", "theme.html", "search.html", "game.html",
    "comments_list.html", "upload-flash.html", "404.html", "403.html", "500.html",
    "user/login.html", "user/auth.html", "user/panel.html",
)  # fmt: skip


@pytest.mark.parametrize("name", ["xxxflash-en", "flashsex-en"])
def test_english_sets_have_every_page(name):
    missing = [t for t in VIEW_TEMPLATES if not (TEMPLATES / name / t).is_file()]
    assert not missing, (name, missing)


def test_english_templates_mirror_russian():
    """Every xxxflash template has an English copy; shared ones with text are overridden."""
    ru, en = TEMPLATES / "xxxflash", TEMPLATES / "xxxflash-en"
    missing = _names(ru) - _names(en)
    assert not missing, f"add English copies to templates/xxxflash-en/: {sorted(missing)}"
    for name in ("403.html", "player.html"):
        assert (en / name).is_file(), name


@pytest.mark.parametrize("name", ["xxxflash-en", "flashsex-en"])
def test_english_templates_have_no_russian(name):
    for path in (TEMPLATES / name).rglob("*.html"):
        found = CYRILLIC.findall(path.read_text(encoding="utf-8"))
        assert not found, (path.name, "".join(found)[:40])


def test_messages_match_across_languages():
    ru = MESSAGES["ru"]
    for lang, messages in MESSAGES.items():
        assert messages.keys() == ru.keys(), lang
        for key, text in messages.items():
            assert sorted(re.findall(r"\{(\w+)\}", text)) == sorted(
                re.findall(r"\{(\w+)\}", ru[key])
            ), (lang, key)


@pytest.mark.parametrize(
    ("n", "expected"),
    [(1, "игра"), (2, "игры"), (5, "игр"), (11, "игр"), (21, "игра"), (22, "игры"), (112, "игр")],
)
def test_russian_plurals(n, expected):
    assert Locale("ru").plural(n, "игра|игры|игр") == expected


def test_english_plurals_numbers_and_messages():
    en = Locale("en")
    assert en.plural(1, "game|games") == "game"
    assert en.plural(3, "game|games") == "games"
    assert en.number(1234567) == "1,234,567"
    assert Locale("ru").number(1234567) == "1 234 567"
    assert en.msg("swf_too_big", n=20) == "The file is larger than 20 MB."


def test_unknown_language_rejected():
    with pytest.raises(ValueError):
        Locale("de")


def test_site_name_accepts_language_suffix():
    from app.config import site_name

    assert site_name("xxxflash-en", "en") == "xxxflash"
    assert site_name("xxxflash", "en") == "xxxflash"
    assert site_name("xxxflash", "ru") == "xxxflash"


def test_missing_language_templates_rejected():
    from app.templating import create_env

    with pytest.raises(ValueError, match="nosuchsite-en"):
        create_env(dataclasses.replace(settings, site="nosuchsite", language="en"))


def test_language_static_dir():
    """flashsex-en is its own design with its own static files; xxxflash-en reuses xxxflash's."""
    en = dataclasses.replace(settings, site="flashsex", language="en")
    assert en.static_dir == BASE_DIR / "static" / "flashsex-en"
    assert dataclasses.replace(en, language="ru").static_dir == BASE_DIR / "static" / "flashsex"
    assert dataclasses.replace(en, site="xxxflash").static_dir == BASE_DIR / "static" / "xxxflash"


@pytest.fixture(params=["xxxflash", "flashsex"])
def en_client(request):
    """Both English sites: xxxflash-en and flashsex-en (nsfwgames.top)."""
    from app.server import create_app

    en = dataclasses.replace(settings, site=request.param, language="en", show_comments=False)
    return create_app(en, name=f"en_{secrets.token_hex(3)}", init_orm=False).asgi_client


async def test_english_site_has_no_russian_ui(en_client):
    theme = await make_theme("Квесты", slug="quest", en="Adventure", game_count=1)
    game = await make_game(
        name="Adventure game", description="An English description", themes=[theme]
    )
    for url in (
        "/",
        "/best/",
        "/best2/",
        "/popular/",
        "/random/",
        "/theme/quest/",
        f"/game/{game.id}/",
        "/login/",
        "/nope/",
    ):
        _, resp = await en_client.get(url)
        assert resp.status in (200, 404), url
        assert '<html lang="en">' in resp.text, url
        # every UI string is translated; only game data may be Russian (none here)
        assert not CYRILLIC.search(resp.text.split("<body", 1)[1]), (
            url,
            CYRILLIC.findall(resp.text)[:5],
        )
    _, resp = await en_client.get("/theme/quest/")
    assert "<h1>Adventure</h1>" in resp.text


async def test_english_site_hides_comments(en_client):
    user = await make_user()
    game = await make_game()
    await translate(game, "Translated game")
    await Comment.create(game=game, user=user, text="Отличная игра", ip="10.0.0.1")

    _, resp = await en_client.get(f"/game/{game.id}/")
    assert resp.status == 200
    assert "Отличная игра" not in resp.text
    assert 'id="comments_list"' not in resp.text
    assert "add-comment" not in resp.text

    _, resp = await en_client.get("/")
    assert "Отличная игра" not in resp.text
    assert "Latest comments" not in resp.text

    _, resp = await en_client.get(f"/get_comments/{game.id}/1/")
    assert resp.status == 404
    _, resp = await en_client.post(
        "/add-comment",
        data={"csrf_token": CSRF, "flash_id": str(game.id), "text": "hi", "email": ""},
        headers=headers(user),
    )
    assert resp.status == 404
    assert await Comment.filter(game_id=game.id).count() == 1


async def test_english_site_shows_only_translated_games(en_client):
    theme = await make_theme("Квесты", slug="quest", en="Adventure")
    done = await make_game(name="Русское название", description="Русское описание", themes=[theme])
    await translate(done, "Mermaid adventure", "A story about a mermaid")
    pending = await make_game(name="Непереведённая игра", themes=[theme])
    failed = await make_game(name="Сломанный перевод", themes=[theme])
    await translate(failed, "", status=TranslationStatus.FAILED)

    _, resp = await en_client.get("/")
    assert "Mermaid adventure" in resp.text
    assert "A story about a mermaid" in resp.text
    assert "Русское название" not in resp.text
    for hidden in (pending, failed):
        assert f"/game/{hidden.id}/" not in resp.text
        _, page = await en_client.get(f"/game/{hidden.id}/")
        assert page.status == 404

    _, resp = await en_client.get(f"/game/{done.id}/")
    assert "<h1>Mermaid adventure</h1>" in resp.text
    _, resp = await en_client.get("/theme/quest/")
    assert "1 game in this genre" in resp.text
    assert '<span class="count">1</span>' in resp.text  # rail counts translated games only


async def test_english_search_uses_translations(en_client):
    game = await make_game(name="Русалка")
    await translate(game, "Little mermaid", "Underwater love story")
    await translate(await make_game(name="Другое"), "Space trip", "Aliens")
    _, resp = await en_client.get("/search/mermaid")
    assert f"/game/{game.id}/" in resp.text
    assert "Space trip" not in resp.text
    _, resp = await en_client.get("/search/stories")  # english stemming
    assert "Little mermaid" in resp.text


async def test_genres_without_english_name_are_hidden(en_client):
    named = await make_theme("Квесты", slug="quest", en="Quests")
    unnamed = await make_theme("Роботы", slug="robots")
    game = await make_game(themes=[named, unnamed])
    await translate(game, "Some game")

    _, resp = await en_client.get("/theme/quest/")
    assert "<h1>Quests</h1>" in resp.text
    assert "/theme/robots/" not in resp.text  # not in the genre menu
    _, resp = await en_client.get("/theme/robots/")
    assert resp.status == 404

    user = await make_user()
    _, resp = await en_client.get("/upload/", headers=headers(user))
    assert f'value="{named.id}"' in resp.text
    assert f'value="{unnamed.id}"' not in resp.text


async def test_admin_edits_genre_names(client):
    staff = await make_user("mod", is_staff=True)
    theme = await make_theme("Квесты", slug="quest")
    _, resp = await client.get("/admin-test/themes/", headers=headers(staff))
    assert 'name="name_en"' in resp.text

    form = {"csrf_token": CSRF, "name": "Квесты", "slug": "quest", "name_en": " Adventure "}
    await client.post(f"/admin-test/themes/{theme.id}/", data=form, headers=headers(staff))
    assert (await ThemeTranslation.get(theme=theme, language="en")).name == "Adventure"

    form["name_en"] = ""  # clearing the name hides the genre on the English site again
    await client.post(f"/admin-test/themes/{theme.id}/", data=form, headers=headers(staff))
    assert not await ThemeTranslation.exists(theme=theme)

    form = {"csrf_token": CSRF, "name": "Роботы", "slug": "robots", "name_en": "Robots"}
    await client.post("/admin-test/themes/", data=form, headers=headers(staff))
    assert (await ThemeTranslation.get(theme__slug="robots")).name == "Robots"


async def test_english_vote_message(en_client):
    game = await make_game()
    await en_client.post("/mark/", data={"pk": str(game.id), "vote": "up"}, headers=headers())
    _, resp = await en_client.post(
        "/mark/", data={"pk": str(game.id), "vote": "up"}, headers=headers()
    )
    assert resp.json == {"success": "You've already voted"}


async def test_admin_theme_row_saves_without_reload(client):
    """admin.js posts a row with Accept: application/json and gets JSON instead of a redirect."""
    staff = await make_user("mod", is_staff=True)
    theme = await make_theme("Квесты", slug="quest", en="Adventure")
    other = await make_theme("Роботы", slug="robots")
    await make_game(themes=[theme])
    ajax = headers(staff, Accept="application/json")
    url = f"/admin-test/themes/{theme.id}/"
    form = {"csrf_token": CSRF, "name": "Квесты 2", "slug": "quest", "sort_order": "3"}
    form |= {"active": "on", "name_en": "Quests"}

    _, resp = await client.post(url, data=form, headers=ajax)
    assert resp.json == {"ok": True, "game_count": 1}
    theme = await Theme.get(id=theme.id)
    assert (theme.name, theme.sort_order) == ("Квесты 2", 3)
    assert (await ThemeTranslation.get(theme=theme)).name == "Quests"

    _, resp = await client.post(url, data=form | {"slug": "robots"}, headers=ajax)
    assert resp.status == 400
    assert resp.json == {"ok": False, "error": "slug already exists"}
    _, resp = await client.post(url, data=form | {"name": " "}, headers=ajax)
    assert resp.json["error"] == "name and slug are required"
    assert (await Theme.get(id=theme.id)).name == "Квесты 2"  # nothing saved

    _, resp = await client.post(url, data=form, headers=headers(staff))  # no JS: redirect
    assert resp.status == 302

    _, resp = await client.post(
        f"/admin-test/themes/{other.id}/", data={"csrf_token": CSRF, "delete": "1"}, headers=ajax
    )
    assert resp.json == {"ok": True, "deleted": True}
    assert not await Theme.exists(id=other.id)

    _, resp = await client.get("/admin-test/themes/", headers=headers(staff))
    assert "data-ajax-row" in resp.text and "admin.js" in resp.text
