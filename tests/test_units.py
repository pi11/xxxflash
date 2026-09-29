import pytest

from app.services.auth import normalize_email
from app.services.paging import page_range
from app.services.rules import (
    comment_rejected,
    compute_xrate,
    should_auto_hide,
    truncate_words,
    vote_value,
)
from app.services.swf import SwfError, is_swf, parse_header
from tests.factories import make_swf


def test_vote_value():
    assert vote_value("up") == 1
    assert vote_value("down") == -1
    assert vote_value("sideways") is None


@pytest.mark.parametrize(
    ("rate", "views", "expected"),
    [(5, 100, 500.0), (5, 0, 50000.0), (0, 10, 0.0), (-3, 10, -3.0)],
)
def test_compute_xrate(rate, views, expected):
    assert compute_xrate(rate, views) == expected


def test_auto_hide_threshold():
    assert not should_auto_hide(-4)
    assert should_auto_hide(-5)


def test_comment_rejected():
    assert comment_rejected("Buy VIAGRA now", ["viagra"])
    assert comment_rejected("Напиши этот коммент", [])
    assert not comment_rejected("отличная игра", ["viagra"])


def test_truncate_words():
    assert truncate_words("a b c", 5) == "a b c"
    assert truncate_words("a b c d", 2) == "a b …"
    assert truncate_words(None, 2) == ""


def test_page_range_window():
    assert page_range(1, 3) == [1, 2, 3]
    assert page_range(1, 50) == list(range(1, 11))
    assert page_range(25, 50) == list(range(20, 30))
    assert page_range(50, 50) == list(range(41, 51))


def test_normalize_email():
    assert normalize_email("  Foo@Example.COM ") == "foo@example.com"
    assert normalize_email("not-an-email") is None
    assert normalize_email("") is None


@pytest.mark.parametrize("compressed", [True, False])
def test_parse_swf_header(compressed):
    info = parse_header(make_swf(800, 600, version=10, as3=True, compressed=compressed))
    assert (info.width, info.height, info.version, info.is_as3) == (800, 600, 10, True)
    assert info.signature == ("CWS" if compressed else "FWS")


def test_parse_swf_as2():
    info = parse_header(make_swf(550, 400, version=7))
    assert (info.width, info.height, info.is_as3) == (550, 400, False)


def test_parse_swf_rejects_garbage():
    assert not is_swf(b"GIF89a")
    with pytest.raises(SwfError):
        parse_header(b"")
    with pytest.raises(SwfError):
        parse_header(b"CWS\x09\x00\x00\x00\x00not-zlib")


def test_tortoise_config_pgbouncer_mode():
    import dataclasses

    from app.config import settings, tortoise_config

    direct = tortoise_config(settings, "app")["connections"]["default"]["credentials"]
    assert direct["schema"] == '"app", ext'
    assert "statement_cache_size" not in direct

    bouncer = dataclasses.replace(settings, db_pgbouncer=True)
    creds = tortoise_config(bouncer, "app")["connections"]["default"]["credentials"]
    assert "schema" not in creds  # PgBouncer rejects the search_path startup parameter
    assert creds["statement_cache_size"] == 0
