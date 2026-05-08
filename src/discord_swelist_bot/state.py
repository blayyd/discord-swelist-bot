from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class SeenRow:
    job_id: str
    first_seen_ts: int


class State:
    def __init__(self, db_path: str | Path = "state.db") -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    job_id TEXT PRIMARY KEY,
                    first_seen_ts INTEGER NOT NULL
                )
                """.strip()
            )

    def has_any_rows(self) -> bool:
        with self._connect() as con:
            row = con.execute("SELECT 1 FROM seen_jobs LIMIT 1").fetchone()
            return row is not None

    def filter_unseen(self, jobs: Sequence[dict]) -> list[dict]:
        if not jobs:
            return []

        ids: list[str] = []
        for j in jobs:
            jid = j.get("id")
            if isinstance(jid, str) and jid:
                ids.append(jid)

        if not ids:
            return []

        with self._connect() as con:
            placeholders = ",".join("?" for _ in ids)
            seen = {
                r[0]
                for r in con.execute(
                    f"SELECT job_id FROM seen_jobs WHERE job_id IN ({placeholders})",
                    ids,
                ).fetchall()
            }

        return [j for j in jobs if isinstance(j.get("id"), str) and j["id"] not in seen]

    def mark_seen(self, job_ids: Iterable[str], *, ts: int | None = None) -> None:
        now = int(ts if ts is not None else time.time())
        rows = [(jid, now) for jid in job_ids if isinstance(jid, str) and jid]
        if not rows:
            return
        with self._connect() as con:
            con.executemany(
                "INSERT OR IGNORE INTO seen_jobs(job_id, first_seen_ts) VALUES(?, ?)",
                rows,
            )

