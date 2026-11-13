# -*- coding: utf-8 -*-
"""
数据爬取层：用 akshare 获取单合约日线，交给 FuturesDB 增量存储
支持：期货具体合约、期货主连、股票指数
"""

import akshare as ak
import pandas as pd
from db import FuturesDB


MIN_VOLUME = 10

class FuturesCrawler:
    def __init__(self, db: FuturesDB = None):
        self.db = db or FuturesDB()

    def update_symbol(self, symbol, force_full=False, verbose=True):
        last_date = None if force_full else self.db.get_last_date(symbol)

        if verbose:
            if last_date:
                print(f"[{symbol}] 库中最新: {last_date}，爬取增量...")
            else:
                print(f"[{symbol}] 库中无记录，爬取全量...")

        # ---------- 区分期货和股票指数 ----------
        is_index = str(symbol).lower().startswith(("sh", "sz"))
        
        try:
            if is_index:
                # 股票指数接口
                df = ak.stock_zh_index_daily(symbol=symbol.lower())
            else:
                # 期货接口
                df = ak.futures_zh_daily_sina(symbol=symbol)
        except Exception as e:
            err_msg = str(e)
            if "Length mismatch" in err_msg:
                if verbose: print(f"[{symbol}] 无数据（合约不存在）")
                return {"symbol": symbol, "status": "无数据", "msg": "该合约不存在或已退市", "新增": 0, "跳过": 0, "总计": 0}
            if verbose: print(f"[{symbol}] 失败: {err_msg[:80]}")
            return {"symbol": symbol, "status": "失败", "msg": err_msg[:80], "新增": 0, "跳过": 0, "总计": 0}

        if df is None or df.empty or len(df.columns) == 0:
            if verbose: print(f"[{symbol}] 无数据（返回为空）")
            return {"symbol": symbol, "status": "无数据", "msg": "该合约不存在或已退市", "新增": 0, "跳过": 0, "总计": 0}

        # 字段对齐
        if is_index:
            # 指数接口通常自带 date, open, high, low, close, volume
            df = df.rename(columns={"date": "date"})
        else:
            if "date" not in df.columns:
                if verbose: print(f"[{symbol}] 无数据（结构异常）")
                return {"symbol": symbol, "status": "无数据", "msg": f"返回结构异常: {df.columns.tolist()}", "新增": 0, "跳过": 0, "总计": 0}

        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        # 过滤低成交量（指数一般成交量很大，不会触发；但过滤一下更安全）
        if "volume" in df.columns:
            before_n = len(df)
            df = df[pd.to_numeric(df["volume"], errors="coerce").fillna(0) >= 0] # 指数数据允许成交量小，这里 >=0 相当于不过滤，只去空
            if verbose and len(df) != before_n:
                print(f"[{symbol}] 过滤异常记录: {before_n - len(df)} 条")

        if df.empty:
            if verbose: print(f"[{symbol}] 过滤后无有效数据")
            return {"symbol": symbol, "status": "无数据", "msg": "无有效记录", "新增": 0, "跳过": 0, "总计": 0}

        # 增量过滤
        if last_date:
            df = df[df["date"] > last_date]
            if df.empty:
                stat = self.db.stats_by_symbol(symbol)
                if verbose: print(f"[{symbol}] 已是最新，无新增")
                return {"symbol": symbol, "status": "已最新", "msg": f"截至 {last_date}", "新增": 0, "跳过": 0, "总计": stat["记录数"]}

        # 补充缺失列（指数没有 hold/settle，db.save 里的 _f 会处理 None）
        for col in ["open", "high", "low", "close", "volume", "hold", "settle"]:
            if col not in df.columns:
                df[col] = None

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
