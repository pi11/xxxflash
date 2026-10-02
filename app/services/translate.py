"""Machine translation of game titles/descriptions through adtr_client.

adtr_client (>= 0.0.7) is synchronous (requests) and translates one text per call, up to
50 000 characters, with an optional `context` (up to 1 000 characters) describing what the text
is. This module adds: a thread-pool bridge for asyncio, retries with backoff on transient errors,
context for game titles (their description) and descriptions (their title), sentence-aware
chunking of over-long texts, and passthrough of texts without Cyrillic (brand names / titles
that are already English).
"""

import asyncio
import hashlib
import logging
import re
from collections.abc import Callable

log = logging.getLogger("app.translate")

MAX_CHARS = 50_000  # adtr_client.MAX_TRANSLATION_LENGTH
MAX_CONTEXT = 1_000  # adtr_client.MAX_CONTEXT_LENGTH
SITE_CONTEXT = (
    "From an archive of retro erotic (adult) Flash games playable in the browser. "
    "Keep it natural for English-speaking players; keep game and brand names as they are."
)
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


def clip(text: str, limit: int) -> str:
    """Shorten to `limit` characters at a word break, marking the cut with an ellipsis."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def title_context(description: str) -> str:
    base = f"{SITE_CONTEXT} The text is the title of a game."
    if not description.strip():
        return base
    lead = f"{base} The game's description: "
    return lead + clip(description, MAX_CONTEXT - len(lead))


def description_context(name: str) -> str:
    return clip(
        f"{SITE_CONTEXT} The text is the description of the game titled “{name}”.", MAX_CONTEXT
    )


# A backend translates one text: (text, source_lang, target_lang, context) -> translated text.
Backend = Callable[[str, str, str, str | None], str]


def adtr_backend(user_id: int, api_key: str, timeout: int = 60) -> Backend:
    from adtr_client import translate

    def call(text: str, source: str, target: str, context: str | None = None) -> str:
        return translate(
            user_id=user_id,
            api_key=api_key,
            text=text,
            source_language=source,
            target_language=target,
            timeout=timeout,
            context=context or None,
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

    async def _one(self, text: str, target: str, context: str | None) -> str:
        attempt = 0
        while True:
            try:
                async with self.semaphore:
                    self.calls += 1
                    result = await asyncio.to_thread(
                        self.backend, text, self.source, target, context
                    )
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

    async def text(self, text: str, target: str, context: str | None = None) -> str:
        """Translate text of any length (chunked); text without Cyrillic is returned as-is."""
        text = (text or "").strip()
        if not needs_translation(text):
            return text
        if context:
            context = clip(context, MAX_CONTEXT)
        chunks = chunk_text(text)
        parts = await asyncio.gather(*(self._one(c, target, context) for c in chunks))
        return " ".join(parts)

    async def game(self, name: str, description: str, target: str) -> tuple[str, str]:
        """Title and description, each translated with the other as context."""
        return await asyncio.gather(
            self.text(name, target, title_context(description)),
            self.text(description, target, description_context(name)),
        )
