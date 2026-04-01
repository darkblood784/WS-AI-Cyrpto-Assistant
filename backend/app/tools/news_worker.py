from __future__ import annotations

import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.tools.news_ingest import run_news_ingest


def main() -> None:
    interval_secs = int(os.getenv("NEWS_POLL_SECS", "15"))  # 10 minutes default

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required")

    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    while True:
        db = SessionLocal()
        try:
            stats = run_news_ingest(db=db)
            print("[news_worker] ok", stats, flush=True)
        except Exception as e:
            print("[news_worker] error", repr(e), flush=True)
        finally:
            db.close()

        time.sleep(interval_secs)


if __name__ == "__main__":
    main()
