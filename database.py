import sqlite3
import os
from datetime import datetime


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sku_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_no TEXT UNIQUE NOT NULL,
                folder_path TEXT NOT NULL,
                image_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sku_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_no TEXT NOT NULL,
                file_name TEXT NOT NULL,
                seq_no INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                FOREIGN KEY (sku_no) REFERENCES sku_index(sku_no)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sku_no ON sku_images(sku_no)")
        # 手机端删除记录（防误删保护）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deleted_skus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_no TEXT UNIQUE NOT NULL,
                deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def sku_exists(self, sku_no):
        conn = self._get_conn()
        row = conn.execute("SELECT id FROM sku_index WHERE sku_no = ?", (sku_no,)).fetchone()
        conn.close()
        return row is not None

    def create_sku(self, sku_no, folder_path, color=""):
        conn = self._get_conn()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 确保 color 列存在
        try:
            conn.execute("ALTER TABLE sku_index ADD COLUMN color TEXT DEFAULT ''")
        except Exception:
            pass
        conn.execute(
            "INSERT INTO sku_index (sku_no, folder_path, image_count, color, created_at, updated_at) VALUES (?, ?, 0, ?, ?, ?)",
            (sku_no, folder_path, color, now, now),
        )
        conn.commit()
        conn.close()

    def add_image(self, sku_no, file_name, seq_no, file_path):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO sku_images (sku_no, file_name, seq_no, file_path) VALUES (?, ?, ?, ?)",
            (sku_no, file_name, seq_no, file_path),
        )
        conn.execute(
            "UPDATE sku_index SET image_count = image_count + 1, updated_at = ? WHERE sku_no = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sku_no),
        )
        conn.commit()
        conn.close()

    def get_sku(self, sku_no):
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sku_index WHERE sku_no = ?", (sku_no,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_skus(self, date=None):
        conn = self._get_conn()
        if date:
            rows = conn.execute(
                "SELECT * FROM sku_index WHERE DATE(created_at) = ? ORDER BY created_at DESC",
                (date,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sku_index ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_images(self, sku_no):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sku_images WHERE sku_no = ? ORDER BY seq_no", (sku_no,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_max_seq(self, sku_no):
        conn = self._get_conn()
        row = conn.execute("SELECT MAX(seq_no) as max_seq FROM sku_images WHERE sku_no = ?", (sku_no,)).fetchone()
        conn.close()
        return row["max_seq"] if row and row["max_seq"] else 0

    def delete_image(self, sku_no, file_name):
        conn = self._get_conn()
        conn.execute("DELETE FROM sku_images WHERE sku_no = ? AND file_name = ?", (sku_no, file_name))
        conn.execute(
            "UPDATE sku_index SET image_count = image_count - 1, updated_at = ? WHERE sku_no = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sku_no),
        )
        conn.commit()
        conn.close()

    def delete_sku(self, sku_no):
        conn = self._get_conn()
        conn.execute("DELETE FROM sku_images WHERE sku_no = ?", (sku_no,))
        conn.execute("DELETE FROM sku_index WHERE sku_no = ?", (sku_no,))
        conn.commit()
        conn.close()

    def mark_deleted(self, sku_no):
        """记录手机端删除的SKU（防误删保护）"""
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO deleted_skus (sku_no) VALUES (?)",
                (sku_no,)
            )
            conn.commit()
        except Exception:
            pass
        conn.close()

    def get_deleted_skus(self):
        """获取所有被手机端删除的SKU编号"""
        conn = self._get_conn()
        rows = conn.execute("SELECT sku_no FROM deleted_skus").fetchall()
        conn.close()
        return {r[0] for r in rows}

    def unmark_deleted(self, sku_no):
        """撤销删除记录"""
        conn = self._get_conn()
        conn.execute("DELETE FROM deleted_skus WHERE sku_no = ?", (sku_no,))
        conn.commit()
        conn.close()

    def search_skus(self, keyword):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sku_index WHERE sku_no LIKE ? ORDER BY created_at DESC",
            (f"%{keyword}%",),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_color(self, sku_no, color):
        conn = self._get_conn()
        conn.execute("UPDATE sku_index SET color = ? WHERE sku_no = ?", (color, sku_no))
        conn.commit()
        conn.close()
