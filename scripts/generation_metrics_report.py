#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = os.path.dirname(os.path.dirname(__file__))
API_ROOT = os.path.join(ROOT, "api")
if API_ROOT not in sys.path:
    sys.path.append(API_ROOT)

from app.core.config import settings  # noqa: E402
from app.services.metrics_report import build_report, fetch_jobs  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize core generation KPIs from terminal jobs.")
    parser.add_argument("--limit", type=int, default=50, help="How many latest terminal jobs to analyze.")
    parser.add_argument("--json-out", type=str, default="", help="Optional path to write JSON summary.")
    parser.add_argument("--md-out", type=str, default="", help="Optional path to write markdown summary.")
    args = parser.parse_args()

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as session:
            jobs = await fetch_jobs(session, limit=max(1, args.limit))
            summary, markdown = build_report(jobs)
    except Exception as exc:
        raise SystemExit(
            f"Failed to load jobs from database ({settings.database_url}). "
            "Ensure DB is running and DATABASE_URL is correct."
        ) from exc
    finally:
        await engine.dispose()

    print(markdown)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as handle:
            handle.write(markdown + "\n")


if __name__ == "__main__":
    asyncio.run(main())
