# -*- coding: utf-8 -*-
"""
雪球策略判定算法（自然日30天滚动观察版）
"""

import math
from dateutil.relativedelta import relativedelta
import pandas as pd

# 颜色常量
COLOR_GREEN  = "green"   # 发生敲出（无论是否敲入）
COLOR_YELLOW = "yellow"  # 有敲入、无敲出、期末 > 期初
COLOR_RED    = "red"     # 有敲入、无敲出、期末 <= 期初
COLOR_BLUE   = "blue"    # 未敲入、未敲出、持有到期
COLOR_GRAY   = "gray"    # 数据不足


def compute_snowball(dates, prices, out_pct, in_pct, duration_weeks,
                     ki_freq, ko_freq, lockup_weeks=0):
    if isinstance(dates, pd.Series):
        dates = dates.tolist()
    if isinstance(prices, pd.Series):
        prices = prices.tolist()

    n = len(dates)
    dt_list = [pd.to_datetime(d) for d in dates]
    last_date = dt_list[-1]
    results = []

    for i in range(n):
        A_date = dt_list[i]
        A_price = float(prices[i])
        out_price = A_price * out_pct / 100.0
        in_price = A_price * in_pct / 100.0

        target_end = A_date + relativedelta(weeks=duration_weeks)
        lockup_end = A_date + relativedelta(weeks=lockup_weeks)

        knocked_in = False
        knocked_out = False
        ko_month = 0
        
        # 精准的时间跨度记录
        hold_days = duration_weeks * 7 
        hold_weeks = duration_weeks
        
        end_price = None

        # 用于“30天滚动月观察”的记录器
        last_ki_cycle = -1
        last_ko_cycle = -1

        for j in range(i + 1, n):
            D_date = dt_list[j]
            
            if D_date > target_end:
                if end_price is None:
                    end_price = float(prices[j - 1]) if j > i else A_price
                break

            end_price = float(prices[j])
            P = float(prices[j])
            
            days_diff = (D_date - A_date).days

            # ---------------- 判定敲出 ----------------
            if D_date >= lockup_end:
                is_ko_day = False
                if ko_freq[0] == "daily":
                    is_ko_day = True
                elif ko_freq[0] == "weekly" and D_date.weekday() == ko_freq[1]:
                    is_ko_day = True
                elif ko_freq[0] == "monthly":
                    # 自然日 30 天滚动逻辑
                    cycle = days_diff // 30
                    if cycle >= 1 and cycle > last_ko_cycle:
                        last_ko_cycle = cycle
                        is_ko_day = True

                if is_ko_day and P >= out_price:
                    knocked_out = True
                    ko_month = _month_diff(A_date, D_date)
                    hold_days = days_diff
                    hold_weeks = max(1, round(days_diff / 7))
                    break

            # ---------------- 判定敲入 ----------------
            is_ki_day = False
            if ki_freq[0] == "daily":
                is_ki_day = True
            elif ki_freq[0] == "weekly" and D_date.weekday() == ki_freq[1]:
                is_ki_day = True
            elif ki_freq[0] == "monthly":
                # 自然日 30 天滚动逻辑
                cycle = days_diff // 30
                if cycle > last_ki_cycle:
                    last_ki_cycle = cycle
                    is_ki_day = True

            if is_ki_day and P <= in_price:
                knocked_in = True

        full_window = last_date >= target_end

        # 颜色判定
        if knocked_out:
            color = COLOR_GREEN
        elif not full_window:
            color = COLOR_GRAY
            hold_days = 0 
            hold_weeks = 0
        else:
            if knocked_in:
                if end_price >= A_price:
                    color = COLOR_YELLOW
                else:
                    color = COLOR_RED
            else:
                color = COLOR_BLUE
            # 没敲出的，按满期算
            hold_days = (target_end - A_date).days
            hold_weeks = duration_weeks

        results.append({
            "index": i,
            "date": dates[i],
            "price": A_price,
            "end_price": end_price,
            "color": color,
            "ko_month": ko_month,
            "hold_days": hold_days,
            "hold_weeks": hold_weeks,
        })

    return results


def _month_diff(d1, d2):
    if d2 <= d1:
        return 0
    delta = relativedelta(d2, d1)
    months = delta.years * 12 + delta.months
    days = delta.days
    total = months + days / 30.0
    rounded = math.ceil(total * 2) / 2
    return max(rounded, 0.5)
