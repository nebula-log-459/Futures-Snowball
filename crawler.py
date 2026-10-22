# -*- coding: utf-8 -*-
"""
数据爬取层：用 akshare 获取单合约日线，交给 FuturesDB 增量存储
"""

import akshare as ak
import pandas as pd
from db import FuturesDB


# 成交量过滤阈值：低于此值的记录不入库
MIN_VOLUME = 10


class FuturesCrawler:
    def __init__(self, db: FuturesDB = None):
        self.db = db or FuturesDB()

    def update_symbol(self, symbol, force_full=False, verbose=True):
        """
        增量更新单个合约：
        - 库中无该合约 或 force_full=True → 爬全量
        - 否则只保留比库中最新日期更新的部分
        返回 dict: {symbol, status, msg, 新增, 跳过, 总计}
        """
        last_date = None if force_full else self.db.get_last_date(symbol)

        if verbose:
            if last_date:
                print(f"[{symbol}] 库中最新: {last_date}，爬取增量...")
            else:
                print(f"[{symbol}] 库中无记录，爬取全量...")

        # 爬取全量（接口本身返回全量）
        try:
            df = ak.futures_zh_daily_sina(symbol=symbol)
        except Exception as e:
            err_msg = str(e)
            if "Length mismatch" in err_msg:
                if verbose:
                    print(f"[{symbol}] 无数据（合约不存在）")
                return {"symbol": symbol, "status": "无数据",
                        "msg": "该合约不存在或已退市",
                        "新增": 0, "跳过": 0, "总计": 0}
            if verbose:
                print(f"[{symbol}] 失败: {err_msg[:80]}")
            return {"symbol": symbol, "status": "失败",
                    "msg": err_msg[:80], "新增": 0, "跳过": 0, "总计": 0}

        # 空数据保护
        if df is None or df.empty or len(df.columns) == 0:
            if verbose:
                print(f"[{symbol}] 无数据（返回为空）")
            return {"symbol": symbol, "status": "无数据",
                    "msg": "该合约不存在或已退市",
                    "新增": 0, "跳过": 0, "总计": 0}

        if "date" not in df.columns:
            if verbose:
                print(f"[{symbol}] 无数据（结构异常）")
            return {"symbol": symbol, "status": "无数据",
                    "msg": f"返回结构异常: {df.columns.tolist()}",
                    "新增": 0, "跳过": 0, "总计": 0}

        # 统一日期格式
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        # ---------- 【新增】过滤低成交量记录 ----------
        if "volume" in df.columns:
            before_n = len(df)
            df = df[pd.to_numeric(df["volume"], errors="coerce").fillna(0) >= MIN_VOLUME]
            filtered_n = before_n - len(df)
            if verbose and filtered_n > 0:
                print(f"[{symbol}] 过滤低成交量记录: {filtered_n} 条")

        if df.empty:
            if verbose:
                print(f"[{symbol}] 过滤后无有效数据")
            return {"symbol": symbol, "status": "无数据",
                    "msg": f"无成交量 >= {MIN_VOLUME} 的记录",
                    "新增": 0, "跳过": 0, "总计": 0}

        # 增量过滤
        if last_date:
            df = df[df["date"] > last_date]
            if df.empty:
                stat = self.db.stats_by_symbol(symbol)
                if verbose:
                    print(f"[{symbol}] 已是最新，无新增")
                return {"symbol": symbol, "status": "已最新",
                        "msg": f"截至 {last_date}",
                        "新增": 0, "跳过": 0, "总计": stat["记录数"]}

        # 写入
        added, skipped = self.db.save(symbol, df)
        stat = self.db.stats_by_symbol(symbol)

        if verbose:
            print(f"[{symbol}] 新增 {added} 条，跳过 {skipped} 条，库中共 {stat['记录数']} 条")

        return {
            "symbol": symbol,
            "status": "更新成功",
            "msg": f"{df['date'].iloc[0]} ~ {df['date'].iloc[-1]}",
            "新增": added,
            "跳过": skipped,
            "总计": stat["记录数"],
        }

    def update_many(self, symbols, force_full=False, verbose=True):
        results = []
        for i, s in enumerate(symbols, 1):
            if verbose:
                print(f"\n=== [{i}/{len(symbols)}] {s} ===")
            r = self.update_symbol(s, force_full=force_full, verbose=verbose)
            results.append(r)
        return results
 


# ==================== 独立测试 ====================
if __name__ == "__main__":
    db = FuturesDB()
    crawler = FuturesCrawler(db)

    # 测试合约清单（全部是真实存在的合约）
    test_symbols = ["RB2410", "CU2410", "AU2412", "M2411", "TA2410", "IF2410"]

    print("=" * 70)
    print("第一次运行：全量爬取")
    print("=" * 70)
    for s in test_symbols:
        r = crawler.update_symbol(s, force_full=True)
        print(f"  → {r['status']}: {r['msg']} | 新增 {r['新增']} | 总计 {r['总计']}")

    print("\n" + "=" * 70)
    print("第二次运行：增量更新（应显示'已最新'）")
    print("=" * 70)
    for s in test_symbols:
        r = crawler.update_symbol(s)
        print(f"  → {r['status']}: {r['msg']} | 新增 {r['新增']}")

    print("\n" + "=" * 70)
    print("数据库整体统计")
    print("=" * 70)
    print(db.stats())

    print("\n各合约统计：")
    for s in db.list_symbols():
        st = db.stats_by_symbol(s)
        print(f"  {s}: {st['记录数']} 条  [{st['最早']} ~ {st['最新']}]")

    print("\n" + "=" * 70)
    print("读取测试：RB2410 最近 5 天")
    print("=" * 70)
    df = db.load("RB2410")
    print(df.tail(5).to_string(index=False))
