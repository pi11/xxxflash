"""Small helpers to create test data and authenticated requests."""

import datetime as dt
import io
import secrets
import struct
import zlib

from itsdangerous import URLSafeTimedSerializer
from PIL import Image

from app.config import settings
from app.models import Compat, Game, GameTranslation, Theme, TranslationStatus, User
from app.web import CSRF_COOKIE, SESSION_COOKIE

CSRF = "test-csrf-token"


async def make_user(username: str | None = None, **kwargs) -> User:
    username = username or f"user_{secrets.token_hex(3)}"
    kwargs.setdefault("email", f"{username}@example.com")
    return await User.create(username=username, **kwargs)


async def make_theme(name: str = "Эротические", slug: str | None = None, **kwargs) -> Theme:
    return await Theme.create(name=name, slug=slug or f"t{secrets.token_hex(3)}", **kwargs)


async def make_game(user: User | None = None, themes=(), **kwargs) -> Game:
    user = user or await make_user()
    kwargs.setdefault("name", f"Game {secrets.token_hex(2)}")
    kwargs.setdefault("description", "Описание игры")
    kwargs.setdefault("swf_path", f"swf/test/{secrets.token_hex(4)}.swf")
    kwargs.setdefault("sha512", secrets.token_hex(64))
    kwargs.setdefault("published_at", dt.date.today() - dt.timedelta(days=1))
    kwargs.setdefault("compat", Compat.OK)
    game = await Game.create(user=user, **kwargs)
    if themes:
        await game.themes.add(*themes)
    return game


async def translate(
    game: Game,
    name: str,
    description: str = "",
    language: str = "en",
    status: TranslationStatus = TranslationStatus.MACHINE,
) -> GameTranslation:
    return await GameTranslation.create(
        game=game, language=language, name=name, description=description, status=status
    )


CLIENT_IP = "198.51.100.10"


def headers(user: User | None = None, ip: str = CLIENT_IP, **extra) -> dict:
    """Request headers: CSRF cookie+header, client IP, optional logged-in session."""
    jar = {CSRF_COOKIE: CSRF}
    if user is not None:
        serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")
        jar[SESSION_COOKIE] = serializer.dumps({"uid": user.id})
    return {
        "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items()),
        "X-CSRFToken": CSRF,
        "X-Forwarded-For": ip,
        **extra,
    }


def _rect(width_px: int, height_px: int) -> bytes:
    values = [0, width_px * 20, 0, height_px * 20]
    nbits = max(v.bit_length() for v in values) + 1  # signed
    bits = f"{nbits:05b}" + "".join(format(v, f"0{nbits}b") for v in values)
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


def make_swf(
    width: int = 640,
    height: int = 480,
    version: int = 9,
    as3: bool = False,
    compressed: bool = True,
    salt: bytes = b"",
) -> bytes:
    body = _rect(width, height) + bytes([0, 24]) + struct.pack("<H", 1)
    # FileAttributes tag (code 69, length 4)
    body += struct.pack("<H", (69 << 6) | 4) + bytes([0x08 if as3 else 0, 0, 0, 0])
    body += struct.pack("<H", 0) + salt  # End tag (+ optional payload for unique hashes)
    length = 8 + len(body)
    if compressed:
        return b"CWS" + bytes([version]) + struct.pack("<I", length) + zlib.compress(body)
    return b"FWS" + bytes([version]) + struct.pack("<I", length) + body


def make_png(size=(20, 20), color=(200, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()
