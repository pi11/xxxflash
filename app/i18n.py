"""Minimal UI translation: Russian source strings, per-language JSON catalogs in app/locales/.

Templates call `_("Новые игры")`; a missing catalog entry falls back to the Russian source, so
game data (titles, descriptions) and untranslated strings still render.

Plurals are written as "one|few|many" Russian forms, e.g. plural(n, "игра|игры|игр"); a catalog
maps the same key to English "singular|plural".
"""

import json
from functools import cache
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
LANGUAGES = ("ru", "en")


@cache
def _catalog(language: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{language}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _ru_plural_index(n: int) -> int:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 1
    return 2


class Translator:
    def __init__(self, language: str = "ru"):
        if language not in LANGUAGES:
            raise ValueError(f"unsupported SITE_LANGUAGE {language!r}; use one of {LANGUAGES}")
        self.language = language
        self.catalog = _catalog(language) if language != "ru" else {}

    def gettext(self, text: str) -> str:
        return self.catalog.get(text, text)

    __call__ = gettext

    def plural(self, n: int, forms: str) -> str:
        if self.language == "ru":
            variants = forms.split("|")
            return variants[min(_ru_plural_index(n), len(variants) - 1)]
        variants = self.gettext(forms).split("|")
        return variants[0] if abs(n) == 1 or len(variants) == 1 else variants[1]

    def number(self, n: int | None) -> str:
        grouped = f"{n or 0:,}"
        return grouped if self.language == "en" else grouped.replace(",", " ")
