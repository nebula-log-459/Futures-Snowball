# -*- coding: utf-8 -*-
"""
数据存储层：SQLite 缓存期货日线数据
表结构: futures_daily(symbol, date, open, high, low, close, volume, hold, settle)
"""

import sqlite3
import pandas as pd
from pathlib import Path


DB_PATH = Path(__file__).parent / "futures.db"


class FuturesDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        self._init_db()

    def _init_db(self):
        """建表 + 建索引"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS futures_daily (
                symbol TEXT NOT NULL,
                date   TEXT NOT NULL,
                open   REAL,
                high   REAL,
                low    REAL,
                close  REAL,
                volume REAL,
                hold   REAL,
                settle REAL,
                PRIMARY KEY (symbol, date)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_date
            ON futures_daily (symbol, date)
        """)
        conn.commit()
        conn.close()

    # ---------- 查询 ----------

    def get_last_date(self, symbol):
        """返回该合约在库中的最新日期，无记录则返回 None"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT MAX(date) FROM futures_daily WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    def get_first_date(self, symbol):
        """返回该合约在库中的最早日期"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT MIN(date) FROM futures_daily WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    def load(self, symbol, start=None, end=None):
        """读取指定合约的日线数据，返回按日期升序的 DataFrame"""
        conn = sqlite3.connect(self.db_path)
        sql = """
            SELECT date, open, high, low, close, volume, hold, settle
            FROM futures_daily WHERE symbol = ?
        """
        params = [symbol]
        if start:
            sql += " AND date >= ?"
            params.append(start)
        if end:
            sql += " AND date <= ?"
            params.append(end)
        sql += " ORDER BY date ASC"
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df

    # ---------- 写入 ----------

    def save(self, symbol, df):
        """
        增量写入，已存在的 (symbol, date) 自动跳过。
        返回: (新增条数, 跳过条数)
        """
        if df is None or df.empty:
            return 0, 0

        # 先查库里已有多少
        before = self._count(symbol)

        conn = sqlite3.connect(self.db_path)
        rows = []
        for _, r in df.iterrows():
            rows.append((
                symbol,
                str(r["date"]),
                self._f(r.get("open")),
                self._f(r.get("high")),
                self._f(r.get("low")),
                self._f(r.get("close")),
                self._f(r.get("volume")),
                self._f(r.get("hold")),
                self._f(r.get("settle")),
            ))
        conn.executemany("""
            INSERT OR IGNORE INTO futures_daily
            (symbol, date, open, high, low, close, volume, hold, settle)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        conn.close()

        after = self._count(symbol)
        return after - before, len(rows) - (after - before)

    def _count(self, symbol):
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT COUNT(*) FROM futures_daily WHERE symbol = ?", (symbol,))
        n = cur.fetchone()[0]
        conn.close()
        return n

    @staticmethod
    def _f(v):
        """安全转 float，None 或 NaN 返回 None"""
        try:
            if v is None or pd.isna(v):
                return None
            return float(v)
        except Exception:
            return None

    # ---------- 统计 ----------

    def list_symbols(self):
        """返回库中所有合约代码"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT DISTINCT symbol FROM futures_daily ORDER BY symbol")
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows

    def stats(self):
        """库整体统计"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT COUNT(DISTINCT symbol), COUNT(*), MIN(date), MAX(date) FROM futures_daily")
        row = cur.fetchone()
        conn.close()
        return {
            "合约数": row[0] or 0,
            "总记录数": row[1] or 0,
            "最早日期": row[2],
            "最新日期": row[3],
        }

    def stats_by_symbol(self, symbol):
        """单个合约统计"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("""
            SELECT COUNT(*), MIN(date), MAX(date)
            FROM futures_daily WHERE symbol = ?
        """, (symbol,))
        row = cur.fetchone()
        conn.close()
        return {
            "记录数": row[0] or 0,
            "最早": row[1],
            "最新": row[2],
        }