"""`python -m app audit-swf`: fill Game.compat / width / height / swf_version / filesize.

Never changes `active`: hiding happens at query time through HIDE_COMPAT.
"""

import csv
from collections import Counter

from app.config import BASE_DIR, Settings
from app.models import Compat, Game
from app.services.swf import SwfError, parse_header

# Header parsing needs only the beginning of the file.
READ_BYTES = 1 << 20


def audit_file(settings: Settings, swf_path: str) -> dict:
    path = settings.media_root / swf_path
    if not path.is_file():
        return {"compat": Compat.MISSING}
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(READ_BYTES)
    try:
        info = parse_header(head)
    except SwfError:
        return {"compat": Compat.BROKEN, "filesize": size}
    return {
        "compat": Compat.AS3 if info.is_as3 else Compat.OK,
        "filesize": size,
        "swf_version": info.version,
        "is_as3": info.is_as3,
        "width": info.width,
        "height": info.height,
    }


async def audit_all(settings: Settings, only_unknown: bool = False) -> Counter:
    qs = Game.all().order_by("id")
    if only_unknown:
        qs = qs.filter(compat=Compat.UNKNOWN)
    games = await qs.only("id", "swf_path", "active")
    counts: Counter = Counter()
    report_dir = BASE_DIR / "var"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"audit-{settings.site}.csv"
    with report_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "active", "compat", "swf_version", "width", "height", "swf_path"])
        for game in games:
            result = audit_file(settings, game.swf_path)
            await Game.filter(id=game.id).update(**result)
            compat = result["compat"]
            counts[(compat.value, game.active)] += 1
            writer.writerow(
                [
                    game.id,
                    game.active,
                    compat.value,
                    result.get("swf_version", ""),
                    result.get("width", ""),
                    result.get("height", ""),
                    game.swf_path,
                ]
            )
    print(f"{'compat':<10}{'active':>8}{'inactive':>10}")
    for compat in Compat:
        a, i = counts[(compat.value, True)], counts[(compat.value, False)]
        if a or i:
            print(f"{compat.value:<10}{a:>8}{i:>10}")
    print(f"report: {report_path}")
    return counts
