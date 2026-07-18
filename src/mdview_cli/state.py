import sqlite3
from pathlib import Path

from .config import data_dir


class DocumentState:
    def __init__(self, path: Path | None = None):
        db_path = path or (data_dir() / "state.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(db_path)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS associations (
                server TEXT NOT NULL,
                path TEXT NOT NULL,
                document_id TEXT NOT NULL,
                share_id TEXT,
                updated_at TEXT,
                PRIMARY KEY (server, path)
            )"""
        )

    @staticmethod
    def canonical(path: Path) -> str:
        return str(path.expanduser().resolve())

    def get(self, server: str, path: Path):
        row = self.connection.execute(
            "SELECT document_id, share_id, updated_at FROM associations WHERE server = ? AND path = ?",
            (server, self.canonical(path)),
        ).fetchone()
        if not row:
            return None
        return {"document_id": row[0], "share_id": row[1], "updated_at": row[2]}

    def put(self, server: str, path: Path, document_id: str, share_id=None, updated_at=None):
        self.connection.execute(
            """INSERT INTO associations (server, path, document_id, share_id, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(server, path) DO UPDATE SET
                 document_id=excluded.document_id,
                 share_id=COALESCE(excluded.share_id, associations.share_id),
                 updated_at=COALESCE(excluded.updated_at, associations.updated_at)""",
            (server, self.canonical(path), document_id, share_id, updated_at),
        )
        self.connection.commit()

    def unlink(self, server: str, path: Path) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM associations WHERE server = ? AND path = ?",
            (server, self.canonical(path)),
        )
        self.connection.commit()
        return cursor.rowcount > 0
