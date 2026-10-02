"""Command line: python -m app <command>."""

import argparse
import asyncio
import socket
import sys

from app.config import settings


def port_in_use(host: str, port: int) -> bool:
    """True if something already listens there.

    With several workers Sanic binds with SO_REUSEPORT, so a second instance on the same port
    would start silently and the kernel would split requests between the two sites.
    """
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ignore TIME_WAIT leftovers
        try:
            sock.bind((host, port))
        except OSError:
            return True
    return False


def startup_line(host: str, port: int, workers: int) -> str:
    return (
        f"site={settings.site} language={settings.language} templates={settings.template_dir} "
        f"static={settings.static_dir} schema={settings.db_schema} "
        f"listen={host}:{port} workers={workers}"
    )


def cmd_serve(args) -> None:
    from sanic import Sanic
    from sanic.log import logger
    from sanic.worker.loader import AppLoader

    from app.server import create_app

    if port_in_use(args.host, args.port):
        sys.exit(
            f"{args.host}:{args.port} is already in use, probably by another site instance. "
            "Give each env file its own PORT."
        )
    # Workers are separate processes; they rebuild the app through the loader's factory.
    loader = AppLoader(factory=create_app)
    app = loader.load()
    logger.info(startup_line(args.host, args.port, args.workers))
    app.prepare(
        host=args.host,
        port=args.port,
        dev=args.dev,
        workers=args.workers,
        access_log=args.dev,
    )
    Sanic.serve(primary=app, app_loader=loader)


async def _with_orm(coro_factory):
    from tortoise import Tortoise

    from app.config import tortoise_config

    await Tortoise.init(config=tortoise_config(settings))
    try:
        return await coro_factory()
    finally:
        await Tortoise.close_connections()


def cmd_migrate(args) -> None:
    from app.db import run_migrations

    asyncio.run(run_migrations(settings))


def cmd_copy_legacy(args) -> None:
    from app.copy_legacy import LegacyCopier

    copier = LegacyCopier(settings, media_root=args.media)
    print(
        f"copying {settings.legacy_schema}.* -> {settings.db_schema}.* (media: {copier.media_root})"
    )
    report = asyncio.run(copier.run(truncate=args.truncate))
    print(f"\n{'table':<14}{'legacy':>10}{'new':>10}")
    for table, (old, new) in report.items():
        print(f"{table:<14}{old:>10}{new:>10}")


def cmd_audit_swf(args) -> None:
    from app.audit import audit_all

    asyncio.run(_with_orm(lambda: audit_all(settings, only_unknown=args.only_unknown)))


def cmd_translate(args) -> None:
    from app.translate_job import run

    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    asyncio.run(
        _with_orm(
            lambda: run(
                settings,
                args.lang,
                limit=args.limit,
                ids=ids,
                force=args.force,
                dry_run=args.dry_run,
                titles_only=args.retitle,
            )
        )
    )


def cmd_update_counts(args) -> None:
    from app.maintenance import update_theme_counts

    asyncio.run(_with_orm(update_theme_counts))
    print("theme counts updated")


def cmd_create_staff(args) -> None:
    from app.models import User

    async def run():
        email = args.email.strip().lower()
        user = await User.get_or_none(email=email)
        if user is None:
            from app.services.auth import create_user_for_email

            user = await create_user_for_email(email)
        user.is_staff = True
        await user.save(update_fields=["is_staff"])
        print(f"{user.username} <{email}> is staff")

    asyncio.run(_with_orm(run))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="run the web server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--dev", action="store_true", help="auto-reload, debug, access log")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("migrate", help="create schemas and apply Tortoise migrations")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("copy-legacy", help="copy legacy Django tables into the app schema")
    p.add_argument("--truncate", action="store_true", help="clear app tables first")
    p.add_argument("--media", help="media root (default: MEDIA_ROOT)")
    p.set_defaults(func=cmd_copy_legacy)

    p = sub.add_parser("audit-swf", help="parse SWF headers, fill compat/width/height")
    p.add_argument("--only-unknown", action="store_true")
    p.set_defaults(func=cmd_audit_swf)

    p = sub.add_parser("translate", help="machine-translate game titles and descriptions")
    p.add_argument("--lang", default="en", help="target language (default: en)")
    p.add_argument("--limit", type=int, help="translate at most N games (most viewed first)")
    p.add_argument("--ids", help="comma-separated game ids")
    p.add_argument("--force", action="store_true", help="redo machine translations too")
    p.add_argument("--dry-run", action="store_true", help="only list what would be translated")
    p.add_argument(
        "--retitle",
        action="store_true",
        help="re-translate the titles of all machine translations (descriptions kept)",
    )
    p.set_defaults(func=cmd_translate)

    p = sub.add_parser("update-counts", help="recompute theme game counts")
    p.set_defaults(func=cmd_update_counts)

    p = sub.add_parser("create-staff", help="grant staff to a user (created if missing)")
    p.add_argument("email")
    p.set_defaults(func=cmd_create_staff)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
