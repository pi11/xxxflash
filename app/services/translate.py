"""Machine translation of game titles/descriptions through adtr_client.

adtr_client (>= 0.0.7) is synchronous (requests) and translates one text per call, up to
50 000 characters, with an optional `context` (up to 1 000 characters) describing what the text
is. This module adds: a thread-pool bridge for asyncio, retries with backoff on transient errors,
context for titles and descriptions, a guard against titles that come back with extra text,
sentence-aware chunking of over-long texts, and passthrough of texts without Cyrillic (brand
names / titles that are already English).

Titles never get the description as context: the API then tends to translate the context too
and returns "Title\n\nA sexy babe named …" (seen on game 5553).
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


TITLE_CONTEXT = (
    f"{SITE_CONTEXT} The text is the title of a game. "
    "Return only the translated title, nothing else."
)
TITLE_MAX = 60  # a title longer than this and 3x the Russian one has picked up extra text
_QUOTES = {'"': '"', "“": "”", "«": "»", "'": "'"}


def title_problem(source: str, result: str) -> str | None:
    """Why a translated title can't be right, or None."""
    if "\n" in result.strip():
        return "line break in title"
    if len(result) > max(TITLE_MAX, 3 * len(source)):
        return f"title too long ({len(result)} chars)"
    return None


def _clean_title(source: str, result: str) -> str:
    """First line only, without quotes the source title doesn't have."""
    lines = [line.strip() for line in result.strip().splitlines() if line.strip()]
    title = lines[0] if lines else ""
    close = _QUOTES.get(title[:1])
    if close and title.endswith(close) and len(title) > 2 and not source.startswith(title[0]):
        title = title[1:-1].strip()
    return title


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

    async def title(self, name: str, target: str) -> str:
        """A game title; extra text after it is dropped, an over-long result retried without
        context, and if it is still too long the game fails (and is retried on the next run)."""
        name = (name or "").strip()
        if not needs_translation(name):
            return name
        title = ""
        for context in (TITLE_CONTEXT, None):
            title = _clean_title(name, await self.text(name, target, context))
            if title and title_problem(name, title) is None:
                return title
            log.warning("title %r came back as %r", name, title[:80])
        raise TranslationError(f"{title_problem(name, title) or 'empty title'}: {title[:100]!r}")

    async def game(self, name: str, description: str, target: str) -> tuple[str, str]:
        """Title and description; the description gets the title as context."""
        return await asyncio.gather(
            self.title(name, target),
            self.text(description, target, description_context(name)),
        )
