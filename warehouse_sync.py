import sqlite3
import os


class WarehouseSync:
    """从仓库系统读取暂存货盘数据"""

    def __init__(self, db_path):
        self.db_path = db_path

    def _get_conn(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"仓库数据库不存在: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_draft_skus(self):
        """获取暂存货盘的SKU列表"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, 货号, 品名, 供应商代码, 颜色, 码数段, 不含税供货价, 含税供货价 "
            "FROM skus WHERE status='draft' AND deleted_at IS NULL "
            "ORDER BY 供应商代码, 货号"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_sku_by_id(self, sku_id):
        """根据ID获取SKU详情"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM skus WHERE id=? AND deleted_at IS NULL", (sku_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def parse_colors(self, color_str):
        """解析颜色字符串，返回颜色列表"""
        if not color_str:
            return []
        # 支持多种分隔符：逗号、斜杠、顿号、空格
        import re
        colors = re.split(r'[,/、，\s]+', color_str.strip())
        return [c.strip() for c in colors if c.strip()]
