"""``python -m app.seeds`` — demo data for the Persian admin panel.

Usage::

    python -m app.seeds                      # seed the demo dataset (7 days of traffic)
    python -m app.seeds --days 30            # a longer usage window
    python -m app.seeds --no-traffic         # configuration only, no usage rows
    python -m app.seeds --reset              # remove every demo row
    python -m app.seeds --allow-production   # only if you really mean it

The command refuses to touch a production database unless ``--allow-production`` is
given, and every row it writes is marked with ``(demo)`` / ``-demo``.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.seeds.demo import DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD, reset_demo, seed_demo


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.seeds", description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete the demo dataset")
    parser.add_argument("--days", type=int, default=7, help="days of demo traffic (default 7)")
    parser.add_argument(
        "--per-day", type=int, default=24, help="demo requests per day (default 24)"
    )
    parser.add_argument("--no-traffic", action="store_true", help="skip usage rows entirely")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="permit seeding a production environment (demo rows are still marked)",
    )
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    if settings.environment == "production" and not args.allow_production:
        raise SystemExit(
            "refusing to seed a production environment; pass --allow-production to override"
        )

    factory = get_session_factory()
    async with factory() as session:
        if args.reset:
            return {"removed": await reset_demo(session)}
        report = await seed_demo(
            session,
            days=args.days,
            with_traffic=not args.no_traffic,
            requests_per_day=args.per_day,
        )
        payload = report.as_dict()
        payload["admin_email"] = DEMO_ADMIN_EMAIL
        payload["admin_password"] = DEMO_ADMIN_PASSWORD
        return payload


def main() -> int:
    args = _parser().parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
