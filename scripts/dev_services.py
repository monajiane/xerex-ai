#!/usr/bin/env python3
"""Embedded development services (PostgreSQL + Redis).

Docker Compose is the reference deployment (see docker-compose.yml). This script
exists so the project can also run in environments without a container runtime,
for example an ephemeral sandbox: it boots a real PostgreSQL and a real Redis via
the ``pgserver`` and ``redislite`` wheels.

State lives outside the repository:

    ~/.local/state/xerex-dev/pgdata     PostgreSQL data directory
    ~/.local/state/xerex-dev/redis.db   Redis dump file

Usage:
    python scripts/dev_services.py start|stop|status|url
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

STATE_DIR = pathlib.Path.home() / ".local" / "state" / "xerex-dev"
PGDATA = STATE_DIR / "pgdata"
REDIS_CONF = STATE_DIR / "redis.conf"
REDIS_PIDFILE = STATE_DIR / "redis.pid"
REDIS_LOGFILE = STATE_DIR / "redis.log"
REDIS_RDB = STATE_DIR / "redis.rdb"
PG_DATABASE = "xerex"
REDIS_PORT = 56379


def _database_url(socket_dir: pathlib.Path) -> str:
    # PostgreSQL listens on a unix socket inside the data directory; asyncpg is
    # pointed to it through the ``host`` query parameter.
    return f"postgresql+asyncpg://postgres@/{PG_DATABASE}?host={socket_dir}"


def _redis_url() -> str:
    return f"redis://127.0.0.1:{REDIS_PORT}/0"


def start_postgres() -> dict[str, str]:
    import pgserver

    PGDATA.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(str(PGDATA), cleanup_mode=None)
    try:
        server.psql(f"CREATE DATABASE {PG_DATABASE};")
    except Exception as exc:  # noqa: BLE001 - already exists is fine
        if "already exists" not in str(exc):
            print(f"postgres: database creation skipped ({exc})", file=sys.stderr)
    return {"service": "postgresql", "url": _database_url(PGDATA), "socket_dir": str(PGDATA)}


def _redis_binary() -> pathlib.Path:
    """Redis server shipped inside the redislite wheel."""
    import redislite

    binary = pathlib.Path(redislite.__file__).parent / "bin" / "redis-server"
    if not binary.exists():  # pragma: no cover - defensive
        raise SystemExit("bundled redis-server binary not found")
    return binary


def _redis_cli() -> pathlib.Path:
    import redislite

    return pathlib.Path(redislite.__file__).parent / "bin" / "redis-cli"


def start_redis() -> dict[str, str]:
    import time

    import redis

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REDIS_CONF.write_text(
        "\n".join(
            [
                f"port {REDIS_PORT}",
                "bind 127.0.0.1",
                "protected-mode no",
                f"dir {STATE_DIR}",
                f"dbfilename {REDIS_RDB.name}",
                f"pidfile {REDIS_PIDFILE}",
                f"logfile {REDIS_LOGFILE}",
                "save \"\"",
                "appendonly no",
                "daemonize yes",
            ]
        )
        + "\n"
    )
    client = redis.Redis(host="127.0.0.1", port=REDIS_PORT, socket_connect_timeout=1)
    try:
        if client.ping():
            return {"service": "redis", "url": _redis_url(), "already_running": "true"}
    except Exception:  # noqa: BLE001 - not running yet
        pass

    import subprocess

    subprocess.run([str(_redis_binary()), str(REDIS_CONF)], check=True)
    for _ in range(50):
        try:
            if client.ping():
                return {"service": "redis", "url": _redis_url()}
        except Exception:  # noqa: BLE001 - retry until the port is up
            time.sleep(0.1)
    raise SystemExit("redis did not start")


def stop_services() -> None:
    try:
        import pgserver

        if PGDATA.exists():
            server = pgserver.get_server(str(PGDATA), cleanup_mode=None)
            server.cleanup()
    except Exception as exc:  # noqa: BLE001
        print(f"postgres stop: {exc}", file=sys.stderr)

    import subprocess

    try:
        subprocess.run(
            [str(_redis_cli()), "-p", str(REDIS_PORT), "shutdown", "nosave"],
            check=False,
            capture_output=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"redis stop: {exc}", file=sys.stderr)


def status() -> dict[str, object]:
    report: dict[str, object] = {}
    try:
        import pgserver

        server = pgserver.get_server(str(PGDATA), cleanup_mode=None)
        version = server.psql("select 1;")
        report["postgresql"] = {"running": bool(version), "url": _database_url(PGDATA)}
    except Exception as exc:  # noqa: BLE001
        report["postgresql"] = {"running": False, "error": str(exc)}

    import redis

    try:
        client = redis.Redis(host="127.0.0.1", port=REDIS_PORT, socket_connect_timeout=1)
        report["redis"] = {"running": client.ping() is True, "url": _redis_url()}
    except Exception as exc:  # noqa: BLE001
        report["redis"] = {"running": False, "error": str(exc)}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Xerex AI embedded dev services")
    parser.add_argument("command", choices=["start", "stop", "status", "url"])
    args = parser.parse_args()

    if args.command == "start":
        payload = [start_postgres(), start_redis()]
        print(json.dumps(payload, indent=2))
    elif args.command == "stop":
        stop_services()
        print("stopped")
    elif args.command == "status":
        print(json.dumps(status(), indent=2))
    else:
        print(json.dumps({"database_url": _database_url(PGDATA), "redis_url": _redis_url()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
