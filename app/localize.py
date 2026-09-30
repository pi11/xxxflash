"""Attach site-language names/descriptions to Game and Theme objects before rendering.

After `localize`, templates use `g.title` / `g.text` / `t.title`; on the Russian site (or when a
translation is missing) those properties fall back to the Russian source fields.
"""

from collections.abc import Iterable

from app.i18n import _catalog
from app.models import Game, GameTranslation, Theme, ThemeTranslation, TranslationStatus
from app.services.paging import Page

PUBLISHED = (TranslationStatus.MACHINE, TranslationStatus.EDITED)


def _collect(value, games: list[Game], themes: list[Theme]) -> None:
    if isinstance(value, Game):
        games.append(value)
        fetched = getattr(value, "_themes", None) or getattr(
            getattr(value, "themes", None), "related_objects", None
        )
        if fetched:
            themes.extend(fetched)
    elif isinstance(value, Theme):
        themes.append(value)
    elif isinstance(value, Page):
        for item in value.object_list:
            _collect(item, games, themes)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _collect(item, games, themes)


async def localize(values: Iterable, language: str) -> None:
    if language == "ru":
        return
    games: list[Game] = []
    themes: list[Theme] = []
    for value in values:
        _collect(value, games, themes)

    if games:
        rows = await GameTranslation.filter(
            game_id__in={g.id for g in games}, language=language, status__in=PUBLISHED
        ).values("game_id", "name", "description")
        by_id = {r["game_id"]: r for r in rows}
        for g in games:
            if tr := by_id.get(g.id):
                g.tr_name, g.tr_description = tr["name"], tr["description"]

    if themes:
        catalog = _catalog(language)
        rows = await ThemeTranslation.filter(
            theme_id__in={t.id for t in themes}, language=language
        ).values("theme_id", "name")
        by_id = {r["theme_id"]: r["name"] for r in rows}
        for t in themes:
            t.tr_name = by_id.get(t.id) or catalog.get(t.name)
