import dataclasses
import glob
import re
import secrets

import pytest

from app.config import BASE_DIR, settings
from app.i18n import Translator, _catalog
from app.models import Comment, ThemeTranslation, TranslationStatus
from tests.factories import CSRF, headers, make_game, make_theme, make_user, translate

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _template_keys() -> set[str]:
    files = glob.glob(str(BASE_DIR / "templates/xxxflash/**/*.html"), recursive=True)
    files += [str(BASE_DIR / "templates/_shared/player.html")]
    files += [str(BASE_DIR / "templates/_shared/403.html")]
    keys = set()
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        keys |= set(re.findall(r'_\("([^"]+)"\)', text))
        keys |= set(re.findall(r'plural\([^,]+,\s*"([^"]+)"\)', text))
    return keys


def _python_keys() -> set[str]:
    keys = {"Вы уже голосовали", "Неверный формат изображения"}
    for path in glob.glob(str(BASE_DIR / "app/**/*.py"), recursive=True):
        with open(path, encoding="utf-8") as fh:
            keys |= set(re.findall(r'_\("([^"]+)"\)', fh.read()))
    return keys


def test_english_catalog_is_complete():
    missing = sorted((_template_keys() | _python_keys()) - set(_catalog("en")))
    assert not missing, f"add these to app/locales/en.json: {missing}"


def test_catalog_placeholders_match():
    for key, value in _catalog("en").items():
        assert re.findall(r"%\(\w+\)s", key) == re.findall(r"%\(\w+\)s", value), key


@pytest.mark.parametrize(
    ("n", "expected"),
    [(1, "игра"), (2, "игры"), (5, "игр"), (11, "игр"), (21, "игра"), (22, "игры"), (112, "игр")],
)
def test_russian_plurals(n, expected):
    assert Translator("ru").plural(n, "игра|игры|игр") == expected


def test_english_plurals_and_numbers():
    en = Translator("en")
    assert en.plural(1, "игра|игры|игр") == "game"
    assert en.plural(3, "игра|игры|игр") == "games"
    assert en.number(1234567) == "1,234,567"
    assert Translator("ru").number(1234567) == "1 234 567"
    assert en("Нет такого ключа") == "Нет такого ключа"  # untranslated falls back to source


def test_unknown_language_rejected():
    with pytest.raises(ValueError):
        Translator("de")


@pytest.fixture
def en_client():
    from app.server import create_app

    en = dataclasses.replace(settings, language="en", show_comments=False)
    return create_app(en, name=f"en_{secrets.token_hex(3)}", init_orm=False).asgi_client


async def test_english_site_has_no_russian_ui(en_client):
    theme = await make_theme("Квесты", slug="quest", game_count=1)
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
        assert not CYRILLIC.search(resp.text.split("<body>", 1)[1]), (
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
    theme = await make_theme("Квесты", slug="quest")
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


async def test_theme_names_from_db_override_catalog(en_client):
    theme = await make_theme("Квесты", slug="quest")
    await ThemeTranslation.create(theme=theme, language="en", name="Quests")
    game = await make_game(themes=[theme])
    await translate(game, "Some game")
    _, resp = await en_client.get("/theme/quest/")
    assert "<h1>Quests</h1>" in resp.text


async def test_english_vote_message(en_client):
    game = await make_game()
    await en_client.post("/mark/", data={"pk": str(game.id), "vote": "up"}, headers=headers())
    _, resp = await en_client.post(
        "/mark/", data={"pk": str(game.id), "vote": "up"}, headers=headers()
    )
    assert resp.json == {"success": "You've already voted"}
