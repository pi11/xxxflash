"""Tortoise models. Tables live in the `DB_SCHEMA` schema (default `app`)."""

import datetime as dt
from enum import StrEnum

from tortoise import fields
from tortoise.indexes import Index
from tortoise.models import Model


def today() -> dt.date:
    return dt.date.today()


class Compat(StrEnum):
    """Ruffle compatibility of a game's SWF, filled by `python -m app audit-swf`."""

    UNKNOWN = "unknown"
    OK = "ok"  # AS1/AS2
    AS3 = "as3"  # ActionScript 3 - may not work in Ruffle
    BROKEN = "broken"  # header does not parse
    MISSING = "missing"  # file not on disk


class User(Model):
    id = fields.IntField(primary_key=True)
    username = fields.CharField(max_length=150, unique=True)
    email = fields.CharField(max_length=254, unique=True, null=True)
    is_staff = fields.BooleanField(default=False)
    is_active = fields.BooleanField(default=True)
    score = fields.IntField(default=0)
    avatar = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login = fields.DatetimeField(null=True)

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return self.username

    @property
    def is_authenticated(self) -> bool:
        return True


class LoginToken(Model):
    token_hash = fields.CharField(max_length=64, primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="login_tokens", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField()
    used_at = fields.DatetimeField(null=True)

    class Meta:
        table = "login_tokens"


class Theme(Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=250)
    slug = fields.CharField(max_length=100, unique=True)
    active = fields.BooleanField(default=True)
    sort_order = fields.IntField(default=0)
    game_count = fields.IntField(default=0)

    games: fields.ManyToManyRelation["Game"]

    class Meta:
        table = "themes"
        ordering = ["-sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Game(Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=150)
    description = fields.TextField(default="")
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="games", on_delete=fields.RESTRICT
    )
    swf_path = fields.CharField(max_length=255)
    thumb_path = fields.CharField(max_length=255, null=True)
    filesize = fields.BigIntField(default=0)
    rate = fields.IntField(default=0)
    views = fields.IntField(default=0)
    xrate = fields.FloatField(default=0)
    active = fields.BooleanField(default=True)
    published_at = fields.DateField(default=today)
    sha512 = fields.CharField(max_length=128, unique=True)
    swf_version = fields.SmallIntField(null=True)
    is_as3 = fields.BooleanField(default=False)
    width = fields.IntField(default=0)
    height = fields.IntField(default=0)
    compat = fields.CharEnumField(Compat, max_length=10, default=Compat.UNKNOWN)
    themes: fields.ManyToManyRelation[Theme] = fields.ManyToManyField(
        "models.Theme",
        related_name="games",
        through="game_themes",
        forward_key="theme_id",
        backward_key="game_id",
    )

    screenshots: fields.ReverseRelation["Screenshot"]

    class Meta:
        table = "games"
        indexes = [
            Index(fields=["active", "published_at"]),
            Index(fields=["rate"]),
            Index(fields=["xrate"]),
            Index(fields=["views"]),
        ]

    def __str__(self) -> str:
        return self.name


class Screenshot(Model):
    id = fields.IntField(primary_key=True)
    game: fields.ForeignKeyRelation[Game] = fields.ForeignKeyField(
        "models.Game", related_name="screenshots", on_delete=fields.CASCADE
    )
    image_path = fields.CharField(max_length=255)

    class Meta:
        table = "screenshots"
        ordering = ["id"]


class Vote(Model):
    id = fields.IntField(primary_key=True)
    game: fields.ForeignKeyRelation[Game] = fields.ForeignKeyField(
        "models.Game", related_name="votes", on_delete=fields.CASCADE
    )
    ip = fields.CharField(max_length=45)
    value = fields.SmallIntField()
    user: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="votes", null=True, on_delete=fields.SET_NULL
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "votes"
        indexes = [Index(fields=["game_id", "ip"])]


class Comment(Model):
    id = fields.IntField(primary_key=True)
    game: fields.ForeignKeyRelation[Game] = fields.ForeignKeyField(
        "models.Game", related_name="comments", on_delete=fields.CASCADE
    )
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="comments", on_delete=fields.CASCADE
    )
    text = fields.TextField()
    ip = fields.CharField(max_length=45, null=True)
    ua = fields.CharField(max_length=250, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "comments"


class Ban(Model):
    ip = fields.CharField(max_length=45, primary_key=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "bans"


class BannedWord(Model):
    word = fields.CharField(max_length=100, primary_key=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "banned_words"
