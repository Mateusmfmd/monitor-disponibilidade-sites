"""Persistência SQLite do histórico de verificações."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .checker import CheckResult


class HistoryStore:
    """Armazena cada tentativa finalizada em uma tabela simples e indexada."""

    def __init__(self, database: Path | str):
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database)
        self._connection.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                name TEXT,
                checked_at TEXT NOT NULL,
                available INTEGER NOT NULL,
                status_code INTEGER,
                response_time_ms REAL,
                attempts INTEGER NOT NULL,
                error TEXT
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_checks_url_checked_at ON checks(url, checked_at DESC)"
        )
        self._connection.commit()

    def record(self, result: CheckResult) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO checks
              (url, name, checked_at, available, status_code, response_time_ms, attempts, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """ ,
            (
                result.url,
                result.name,
                result.checked_at,
                int(result.available),
                result.status_code,
                result.response_time_ms,
                result.attempts,
                result.error,
            ),
        )
        self._connection.commit()
        return int(cursor.lastrowid)

    def history(self, url: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, int(limit))
        if url:
            cursor = self._connection.execute(
                """
                SELECT id, url, name, checked_at, available, status_code,
                       response_time_ms, attempts, error
                  FROM checks WHERE url = ? ORDER BY checked_at DESC, id DESC LIMIT ?
                """,
                (url, limit),
            )
        else:
            cursor = self._connection.execute(
                """
                SELECT id, url, name, checked_at, available, status_code,
                       response_time_ms, attempts, error
                  FROM checks ORDER BY checked_at DESC, id DESC LIMIT ?
                """,
                (limit,),
            )
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["available"] = bool(item["available"])
            rows.append(item)
        return rows

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "HistoryStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
