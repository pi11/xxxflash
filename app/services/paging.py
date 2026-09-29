"""Pagination with the legacy semantics: `?p=N`, out-of-range pages clamp to the last page."""

from dataclasses import dataclass, field
from typing import Any

from sanic.exceptions import NotFound
from tortoise.queryset import QuerySet


@dataclass
class Page:
    number: int
    num_pages: int
    count: int
    object_list: list[Any] = field(default_factory=list)
    page_range: list[int] = field(default_factory=list)

    @property
    def has_previous(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.num_pages

    @property
    def previous_page_number(self) -> int:
        return self.number - 1

    @property
    def next_page_number(self) -> int:
        return self.number + 1


def page_param(request, name: str = "p") -> int:
    """Legacy: non-integer page -> 404, missing -> 1."""
    raw = request.args.get(name, "1")
    try:
        return int(raw)
    except ValueError:
        raise NotFound("bad page") from None


def page_range(number: int, num_pages: int, links: int = 10) -> list[int]:
    """Window of `links` page numbers around the current page."""
    start = max(1, number - links // 2)
    end = min(num_pages, start + links - 1)
    start = max(1, end - links + 1)
    return list(range(start, end + 1))


async def paginate(qs: QuerySet, number: int, per_page: int, links: int = 10) -> Page:
    count = await qs.count()
    num_pages = max(1, -(-count // per_page))
    if number < 1 or number > num_pages:
        number = num_pages  # legacy EmptyPage handling: deliver the last page
    items = await qs.offset((number - 1) * per_page).limit(per_page)
    return Page(
        number=number,
        num_pages=num_pages,
        count=count,
        object_list=list(items),
        page_range=page_range(number, num_pages, links),
    )
