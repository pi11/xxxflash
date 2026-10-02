"""Machine translation job — uses a fake backend, never the real API."""

import dataclasses

import pytest
import requests

from app.config import settings
from app.models import GameTranslation, ThemeTranslation, TranslationStatus
from app.services.translate import (
    MAX_CHARS,
    MAX_CONTEXT,
    MachineTranslator,
    TranslationError,
    chunk_text,
    clip,
)
from app.translate_job import find_candidates, run
from tests.factories import make_game, make_theme


class FakeBackend:
    def __init__(self, fail_on: str | None = None, transient_failures: int = 0):
        self.calls: list[str] = []
        self.contexts: dict[str, str | None] = {}
        self.fail_on = fail_on
        self.transient_failures = transient_failures

    def __call__(self, text: str, source: str, target: str, context: str | None = None) -> str:
        self.calls.append(text)
        self.contexts[text] = context
        assert len(text) <= MAX_CHARS
        assert context is None or 0 < len(context) <= MAX_CONTEXT
        if self.transient_failures:
            self.transient_failures -= 1
            resp = requests.Response()
            resp.status_code = 503
            raise requests.HTTPError("503 busy", response=resp)
        if self.fail_on and self.fail_on in text:
            resp = requests.Response()
            resp.status_code = 400
            raise requests.HTTPError("400 bad", response=resp)
        return f"EN[{text}]"


def translator(backend) -> MachineTranslator:
    return MachineTranslator(backend, concurrency=2, retries=2, backoff=0)


CFG = dataclasses.replace(settings, translate_concurrency=2)


def test_chunk_text_prefers_sentences():
    sentence = "Это предложение про игру номер {}. "
    text = "".join(sentence.format(i) for i in range(20)).strip()
    chunks = chunk_text(text, limit=300)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    assert all(c.endswith(".") for c in chunks)
    assert " ".join(chunks) == text


def test_chunk_text_hard_split():
    text = "слово " * 200
    chunks = chunk_text(text, limit=300)
    assert all(len(c) <= 300 for c in chunks)
    assert " ".join(chunks).split() == text.split()
    assert chunk_text("а" * 700, limit=300) == ["а" * 300, "а" * 300, "а" * 100]
    assert chunk_text(text) == [text.strip()]  # the API takes up to 50 000 characters
    assert chunk_text("   ") == []


def test_clip_cuts_at_a_word():
    assert clip("short  text", 50) == "short text"
    assert clip("один два три четыре", 12) == "один два…"
    assert len(clip("слово " * 500, MAX_CONTEXT)) <= MAX_CONTEXT


async def test_translator_passthrough_retry_and_errors():
    backend = FakeBackend(transient_failures=1)
    tr = translator(backend)
    assert await tr.text("Meet'n'Fuck: Lavindor Kingdom", "en") == "Meet'n'Fuck: Lavindor Kingdom"
    assert backend.calls == []  # no Cyrillic -> no API call
    assert await tr.text("Привет", "en") == "EN[Привет]"
    assert backend.calls == ["Привет", "Привет"]  # one transient 503, then success

    with pytest.raises(TranslationError):
        await translator(FakeBackend(fail_on="плохо")).text("плохо", "en")  # 400: no retry


async def test_translate_job_end_to_end(database):
    theme = await make_theme("Квесты", slug="quest")
    popular = await make_game(name="Популярная", description="Описание", views=1000, themes=[theme])
    latin = await make_game(name="Bootycall 2", description="Английское описание", views=10)
    long_desc = "Длинное описание игры. " * 30
    long = await make_game(name="Длинная", description=long_desc, views=5)
    broken = await make_game(name="Сломается", description="тут плохо", views=1)
    inactive = await make_game(name="Неактивная", active=False, views=0)

    backend = FakeBackend(fail_on="плохо")
    results = await run(CFG, "en", translator=translator(backend))
    assert results[TranslationStatus.MACHINE] == 4
    assert results[TranslationStatus.FAILED] == 1

    rows = {t.game_id: t for t in await GameTranslation.filter(language="en")}
    assert rows[popular.id].name == "EN[Популярная]"
    assert rows[latin.id].name == "Bootycall 2"  # copied, not translated
    assert rows[long.id].description == f"EN[{long_desc.strip()}]"  # one call, not chunked
    # each text is sent with context: titles with their description, descriptions with the title
    assert "Описание" in backend.contexts["Популярная"]
    assert "“Популярная”" in backend.contexts["Описание"]
    assert len(backend.contexts["Длинная"]) <= MAX_CONTEXT  # long description clipped
    assert rows[broken.id].status == TranslationStatus.FAILED and rows[broken.id].error
    assert rows[inactive.id].status == TranslationStatus.MACHINE  # all games, not only active

    assert not await ThemeTranslation.exists()  # genre names are entered in the admin

    # second run: only the failed one is retried
    backend2 = FakeBackend()
    results = await run(CFG, "en", translator=translator(backend2))
    assert results[TranslationStatus.MACHINE] == 1
    assert sorted(backend2.calls) == ["Сломается", "тут плохо"]  # translated concurrently

    # editing the Russian source re-translates; moderator-edited rows are never touched
    popular.name = "Популярная 2"
    await popular.save()
    await GameTranslation.filter(game_id=latin.id).update(
        status=TranslationStatus.EDITED, name="Hand-made title"
    )
    latin.name = "Bootycall 3"
    await latin.save()
    reasons = {c.id: c.reason for c in await find_candidates("en")}
    assert reasons == {popular.id: "changed"}
    await run(CFG, "en", translator=translator(FakeBackend()))
    assert (await GameTranslation.get(game_id=popular.id)).name == "EN[Популярная 2]"
    assert (await GameTranslation.get(game_id=latin.id)).name == "Hand-made title"


async def test_translate_job_limit_order_and_dry_run(database):
    low = await make_game(name="Мало просмотров", views=1)
    high = await make_game(name="Много просмотров", views=500)
    backend = FakeBackend()
    assert await run(CFG, "en", limit=1, dry_run=True, translator=translator(backend)) == {}
    assert backend.calls == []
    await run(CFG, "en", limit=1, translator=translator(backend))
    assert await GameTranslation.filter(game_id=high.id).exists()  # most viewed first
    assert not await GameTranslation.filter(game_id=low.id).exists()


async def test_admin_edit_translation_marks_edited(client):
    from tests.factories import CSRF, headers, make_user

    staff = await make_user("mod", is_staff=True)
    game = await make_game(name="Русское")
    form = {
        "csrf_token": CSRF,
        "name": "Русское",
        "description": "d",
        "published_at": "2020-01-02",
        "active": "on",
        "tr_en_name": "Hand-made",
        "tr_en_description": "By a human",
    }
    _, resp = await client.post(f"/admin-test/games/{game.id}/", data=form, headers=headers(staff))
    assert resp.status == 200, resp.text[:300]
    row = await GameTranslation.get(game_id=game.id, language="en")
    assert (row.name, row.status) == ("Hand-made", TranslationStatus.EDITED)
    assert "edited" in resp.text

    # saving again without changes keeps it; machine runs skip it
    assert await find_candidates("en", ids=[game.id]) == []
