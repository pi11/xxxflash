"""SWF header parsing: signature, version, stage size, ActionScript 3 flag."""

import hashlib
import lzma
import struct
import zlib
from dataclasses import dataclass

SIGNATURES = (b"FWS", b"CWS", b"ZWS")
TAG_FILE_ATTRIBUTES = 69
AS3_FLAG = 0x08
# Enough decompressed bytes for the header RECT and the first tags.
_HEAD = 4096


class SwfError(ValueError):
    pass


@dataclass(frozen=True)
class SwfInfo:
    signature: str
    version: int
    width: int
    height: int
    frame_rate: float
    is_as3: bool


def is_swf(data: bytes) -> bool:
    return data[:3] in SIGNATURES


def sha512_hex(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


def _body(data: bytes) -> bytes:
    sig = data[:3]
    if sig == b"FWS":
        return data[8 : 8 + _HEAD]
    if sig == b"CWS":
        return zlib.decompressobj().decompress(data[8:], _HEAD)
    if sig == b"ZWS":
        # 8-byte header, u32 compressed length, 5-byte LZMA props, then the raw LZMA stream.
        # Rebuild an .lzma ("alone") header: props + unknown size (-1).
        if len(data) < 17:
            raise SwfError("truncated LZMA header")
        alone = data[12:17] + b"\xff" * 8 + data[17:]
        return lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(alone, _HEAD)
    raise SwfError("not a SWF file")


def _read_bits(buf: bytes, bitpos: int, nbits: int, signed: bool) -> tuple[int, int]:
    value = 0
    for _ in range(nbits):
        byte = buf[bitpos >> 3]
        bit = (byte >> (7 - (bitpos & 7))) & 1
        value = (value << 1) | bit
        bitpos += 1
    if signed and nbits and value & (1 << (nbits - 1)):
        value -= 1 << nbits
    return value, bitpos


def parse_header(data: bytes) -> SwfInfo:
    if len(data) < 9 or not is_swf(data):
        raise SwfError("not a SWF file")
    version = data[3]
    try:
        body = _body(data)
    except (zlib.error, lzma.LZMAError, EOFError) as exc:
        raise SwfError(f"cannot decompress: {exc}") from exc
    if len(body) < 2:
        raise SwfError("truncated body")
    try:
        nbits = body[0] >> 3
        pos = 5
        xmin, pos = _read_bits(body, pos, nbits, True)
        xmax, pos = _read_bits(body, pos, nbits, True)
        ymin, pos = _read_bits(body, pos, nbits, True)
        ymax, pos = _read_bits(body, pos, nbits, True)
        offset = (pos + 7) // 8
        rate_frac, rate_int = body[offset], body[offset + 1]
        offset += 4  # frame rate (u8.u8) + frame count (u16)
    except IndexError as exc:
        raise SwfError("truncated header") from exc

    is_as3 = False
    # FileAttributes must be the first tag in SWF 8+; look at the first few tags anyway.
    for _ in range(4):
        if offset + 2 > len(body):
            break
        (code_len,) = struct.unpack_from("<H", body, offset)
        code, length = code_len >> 6, code_len & 0x3F
        offset += 2
        if length == 0x3F:
            if offset + 4 > len(body):
                break
            (length,) = struct.unpack_from("<I", body, offset)
            offset += 4
        if code == TAG_FILE_ATTRIBUTES:
            is_as3 = offset < len(body) and bool(body[offset] & AS3_FLAG)
            break
        offset += length

    return SwfInfo(
        signature=data[:3].decode(),
        version=version,
        width=round((xmax - xmin) / 20),
        height=round((ymax - ymin) / 20),
        frame_rate=rate_int + rate_frac / 256,
        is_as3=is_as3,
    )
