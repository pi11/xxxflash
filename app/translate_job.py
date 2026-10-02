"""`python -m app translate --lang en`: machine-translate game titles and descriptions.

Idempotent: a game is (re)translated only when it has no translation, its Russian source changed
(source_hash), or the last attempt failed. Rows a moderator edited are never overwritten.
Popular active games go first, so a partial run (--limit) covers what visitors see most.
"""

import asyncio
import logging
import time
from collections import Counter
from dataclasses import dataclass

from app.config import Settings
from app.models import Game, GameTranslation, TranslationStatus
from app.services.translate import (
    MachineTranslator,
    TranslationError,
    adtr_backend,
    source_hash,
)

log = logging.getLogger("app.translate")


@dataclass
class Candidate:
    id: int
    name: str
    description: str
    source_hash: str
    reason: str  # new | changed | failed | forced


def make_translator(settings: Settings) -> MachineTranslator:
    if not settings.adtr_user_id or not settings.adtr_api_key:
        raise SystemExit("ADTR_USER_ID and ADTR_API_KEY must be set in .env")
    return MachineTranslator(
        adtr_backend(settings.adtr_user_id, settings.adtr_api_key),
        concurrency=settings.translate_concurrency,
    )


async def find_candidates(
    language: str, ids: list[int] | None = None, force: bool = False
) -> list[Candidate]:
    qs = Game.all()
    if ids:
        qs = qs.filter(id__in=ids)
    games = await qs.order_by("-active", "-views", "id").values("id", "name", "description")
    existing = {
        row["game_id"]: row
        for row in await GameTranslation.filter(language=language).values(
            "game_id", "status", "source_hash"
        )
    }
    out = []
    for g in games:
        h = source_hash(g["name"], g["description"])
        tr = existing.get(g["id"])
        if tr is None:
            reason = "new"
        elif tr["status"] == TranslationStatus.EDITED:
            continue  # moderator's text wins, even if the source changed
        elif tr["status"] == TranslationStatus.FAILED:
            reason = "failed"
        elif tr["source_hash"] != h:
            reason = "changed"
        elif force:
            reason = "forced"
        else:
            continue
        out.append(Candidate(g["id"], g["name"], g["description"], h, reason))
    return out


async def translate_game(
    translator: MachineTranslator, cand: Candidate, language: str
) -> TranslationStatus:
    try:
        name, description = await translator.game(cand.name, cand.description, language)
    except TranslationError as exc:
        log.warning("game %s: %s", cand.id, exc)
        await GameTranslation.update_or_create(
            game_id=cand.id,
            language=language,
            defaults={
                "status": TranslationStatus.FAILED,
                "error": str(exc)[:1000],
                "source_hash": cand.source_hash,
            },
        )
        return TranslationStatus.FAILED
    await GameTranslation.update_or_create(
        game_id=cand.id,
        language=language,
        defaults={
            "name": name[:300],
            "description": description,
            "status": TranslationStatus.MACHINE,
            "error": None,
            "source_hash": cand.source_hash,
        },
    )
    return TranslationStatus.MACHINE


async def run(
    settings: Settings,
    language: str,
    limit: int | None = None,
    ids: list[int] | None = None,
    force: bool = False,
    dry_run: bool = False,
    translator: MachineTranslator | None = None,
) -> Counter:
    if language == "ru":
        raise SystemExit("Russian is the source language; pick a target such as --lang en")
    candidates = await find_candidates(language, ids=ids, force=force)
    reasons = Counter(c.reason for c in candidates)
    todo = candidates[:limit] if limit else candidates
    print(
        f"{language}: {len(candidates)} games need translation "
        f"({', '.join(f'{k} {v}' for k, v in sorted(reasons.items())) or 'none'}); "
        f"this run: {len(todo)}"
    )
    if dry_run:
        for c in todo[:20]:
            print(f"  #{c.id} [{c.reason}] {c.name}")
        return Counter()

    translator = translator or make_translator(settings)
    results: Counter = Counter()
    started = time.monotonic()
    # One game at a time per worker; the translator's semaphore bounds API concurrency.
    queue: asyncio.Queue[Candidate] = asyncio.Queue()
    for c in todo:
        queue.put_nowait(c)

    async def worker():
        while not queue.empty():
            cand = queue.get_nowait()
            results[await translate_game(translator, cand, language)] += 1
            n = sum(results.values())
            if n % 25 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} done ({time.monotonic() - started:.0f}s)")

    await asyncio.gather(*(worker() for _ in range(max(1, settings.translate_concurrency))))
    print(
        f"done: {results[TranslationStatus.MACHINE]} translated, "
        f"{results[TranslationStatus.FAILED]} failed, {translator.calls} API calls, "
        f"{time.monotonic() - started:.0f}s"
    )
    return results
