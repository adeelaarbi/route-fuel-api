#!/usr/bin/env python
"""Production-friendly Granian launcher for local runs and Docker.

Granian serves the Django WSGI application directly. The launcher keeps all
runtime knobs in environment variables so Docker, CI, and local demos can use
the same entrypoint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def getenv_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def getenv_int(name: str, default: int, minimum: int = 1) -> str:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return str(default)

    try:
        value = int(raw_value)
    except ValueError:
        print(
            f"Invalid {name}={raw_value!r}; expected an integer. Using {default}.",
            file=sys.stderr,
        )
        return str(default)

    if value < minimum:
        print(
            f"Invalid {name}={value}; expected >= {minimum}. Using {default}.",
            file=sys.stderr,
        )
        return str(default)

    return str(value)


def build_command() -> list[str]:
    host = os.getenv("HOST", os.getenv("GRANIAN_HOST", "0.0.0.0"))
    port = os.getenv("PORT", os.getenv("GRANIAN_PORT", "8000"))

    # Keep WEB_CONCURRENCY support because many container platforms provide it.
    workers = getenv_int("GRANIAN_WORKERS", int(os.getenv("WEB_CONCURRENCY", "1")))

    # WSGI apps use Python blocking threads. Granian may otherwise auto-select a
    # very high ceiling, which can trigger warnings and overrun DB connections.
    blocking_threads = getenv_int("GRANIAN_BLOCKING_THREADS", 8)

    # Backpressure limits how many requests/connections Granian pushes into each
    # worker. For this assignment API, 32 per worker is a safe default: enough for
    # demos/load tests, but not so high that Django/Postgres are flooded.
    backpressure = getenv_int("GRANIAN_BACKPRESSURE", 32)

    log_level = os.getenv("GRANIAN_LOG_LEVEL", "info")
    interface = os.getenv("GRANIAN_INTERFACE", "wsgi")
    application = os.getenv("GRANIAN_APP", "config.wsgi:application")

    command = [
        "granian",
        "--interface",
        interface,
        "--host",
        host,
        "--port",
        port,
        "--workers",
        workers,
        "--blocking-threads",
        blocking_threads,
        "--backpressure",
        backpressure,
        "--log-level",
        log_level,
        "--access-log",
        application,
    ]

    if getenv_bool("DJANGO_DEBUG", default=False) or getenv_bool("GRANIAN_RELOAD", default=False):
        command.insert(-1, "--reload")

    return command


def main() -> int:
    if shutil.which("granian") is None:
        print(
            "Granian is not installed. Run `pip install -r requirements.txt` first.",
            file=sys.stderr,
        )
        return 127

    return subprocess.call(build_command())


if __name__ == "__main__":
    sys.exit(main())
