"""Machine translation of game titles/descriptions through adtr_client.

adtr_client is synchronous (requests), translates one text per call and rejects texts longer
than 300 characters. This module adds: a thread-pool bridge for asyncio, retries with backoff on
transient errors, sentence-aware chunking of long texts, and passthrough of titles that contain
no Cyrillic (brand names / titles that are already English).
"""

import asyncio
import hashlib
import logging
import re
from collections.abc import Callable

log = logging.getLogger("app.translate")

MAX_CHARS = 300
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
# Sentence ends, then line breaks, then commas/semicolons, then spaces.
_SPLITTERS = [re.compile(r"(?<=[.!?…])\s+"), re.compile(r"\n+"), re.compile(r"(?<=[,;:])\s+")]

RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class TranslationError(RuntimeError):
    pass


def source_hash(name: str, description: str) -> str:
    return hashlib.sha256(f"{name}\x00{description}".encode()).hexdigest()


def needs_translation(text: str) -> bool:
    return bool(CYRILLIC.search(text or ""))


def chunk_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split text into pieces <= limit, preferring sentence, line, clause, then word breaks."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    def split(piece: str, level: int) -> list[str]:
        if len(piece) <= limit:
            return [piece]
        if level < len(_SPLITTERS):
            parts = [p for p in _SPLITTERS[level].split(piece) if p.strip()]
            if len(parts) > 1:
                return pack(parts, level)
            return split(piece, level + 1)
        # last resort: hard split on spaces / characters
        words, out, cur = piece.split(" "), [], ""
        for w in words:
            while len(w) > limit:
                out.append(w[:limit])
                w = w[limit:]
            cand = f"{cur} {w}".strip()
            if len(cand) > limit:
                out.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            out.append(cur)
        return out

    def pack(parts: list[str], level: int) -> list[str]:
        out, cur = [], ""
        for part in parts:
            for sub in split(part.strip(), level + 1):
                cand = f"{cur} {sub}".strip() if cur else sub
                if len(cand) > limit:
                    out.append(cur)
                    cur = sub
                else:
                    cur = cand
        if cur:
            out.append(cur)
        return out

    return [c for c in split(text, 0) if c]


def _is_transient(exc: Exception) -> bool:
    try:
        import requests
    except ImportError:  # pragma: no cover
        return False
    if isinstance(exc, requests.HTTPError):
        status = getattr(exc.response, "status_code", None)
        return status in RETRY_STATUSES
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


# A backend translates one short text: (text, source_lang, target_lang) -> translated text.
Backend = Callable[[str, str, str], str]


def adtr_backend(user_id: int, api_key: str, timeout: int = 60) -> Backend:
    from adtr_client import translate

    def call(text: str, source: str, target: str) -> str:
        return translate(
            user_id=user_id,
            api_key=api_key,
            text=text,
            source_language=source,
            target_language=target,
            timeout=timeout,
        )

    return call


class MachineTranslator:
    """Async front-end over a sync backend: concurrency limit, retries, chunking."""

    def __init__(
        self,
        backend: Backend,
        concurrency: int = 4,
        retries: int = 3,
        backoff: float = 2.0,
        source: str = "ru",
    ):
        self.backend = backend
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.retries = retries
        self.backoff = backoff
        self.source = source
        self.calls = 0

    async def _one(self, text: str, target: str) -> str:
        attempt = 0
        while True:
            try:
                async with self.semaphore:
                    self.calls += 1
                    result = await asyncio.to_thread(self.backend, text, self.source, target)
            except Exception as exc:  # noqa: BLE001 - classify below
                attempt += 1
                if attempt > self.retries or not _is_transient(exc):
                    raise TranslationError(f"{type(exc).__name__}: {exc}") from exc
                delay = self.backoff * 2 ** (attempt - 1)
                log.warning("transient translate error (%s), retry in %.0fs", exc, delay)
                await asyncio.sleep(delay)
                continue
            result = (result or "").strip()
            if not result:
                raise TranslationError("empty translation")
            return result

    async def text(self, text: str, target: str) -> str:
        """Translate text of any length (chunked); text without Cyrillic is returned as-is."""
        text = (text or "").strip()
        if not needs_translation(text):
            return text
        chunks = chunk_text(text)
        parts = await asyncio.gather(*(self._one(c, target) for c in chunks))
        return " ".join(parts)

    async def game(self, name: str, description: str, target: str) -> tuple[str, str]:
        return await asyncio.gather(self.text(name, target), self.text(description, target))
