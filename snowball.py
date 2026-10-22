# -*- coding: utf-8 -*-
"""
雪球策略判定算法（最新逻辑）
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
    """
    参数:
        dates: list 或 pd.Series
        prices: list 或 pd.Series
        out_pct, in_pct: 敲出/敲入百分比
        duration_weeks: 总时长(周)
        ki_freq, ko_freq: 观察频率 tuple 如 ("weekly", 0), ("monthly", 1)
        lockup_weeks: 锁定期(周)
    """
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

        # 目标到期日与锁定期边界
        target_end = A_date + relativedelta(weeks=duration_weeks)
        lockup_end = A_date + relativedelta(weeks=lockup_weeks)

        knocked_in = False
        knocked_out = False
        ko_month = 0

        current_month = None
        month_day_count = 0
        end_price = None

        for j in range(i + 1, n):
            D_date = dt_list[j]
            
            # 超出目标周期，记录期末价并停止遍历
            if D_date > target_end:
                # 如果前一天还没被赋值，说明前一天就是窗口内的最后一天
                if end_price is None:
                    end_price = float(prices[j - 1]) if j > i else A_price
                break

            # 记录每天的价格，随着遍历不断更新，直到到达窗口结尾
            end_price = float(prices[j])

            # 统计当月第几个交易日
            if D_date.month != current_month:
                current_month = D_date.month
                month_day_count = 1
            else:
                month_day_count += 1

            P = float(prices[j])

            # ---------- 1. 判定敲出 (优先级最高) ----------
            if D_date >= lockup_end:
                is_ko_day = False
                if ko_freq[0] == "daily":
                    is_ko_day = True
                elif ko_freq[0] == "weekly" and D_date.weekday() == ko_freq[1]:
                    is_ko_day = True
                elif ko_freq[0] == "monthly" and month_day_count == ko_freq[1]:
                    is_ko_day = True

                if is_ko_day and P >= out_price:
                    knocked_out = True
                    ko_month = _month_diff(A_date, D_date)
                    break

            # ---------- 2. 判定敲入 ----------
            is_ki_day = False
            if ki_freq[0] == "daily":
                is_ki_day = True
            elif ki_freq[0] == "weekly" and D_date.weekday() == ki_freq[1]:
                is_ki_day = True
            elif ki_freq[0] == "monthly" and month_day_count == ki_freq[1]:
                is_ki_day = True

            if is_ki_day and P <= in_price:
                knocked_in = True

        # 如果循环到数据末尾都没超过 target_end，说明数据缺失
        full_window = last_date >= target_end

        # ---------- 颜色判定 (新逻辑) ----------
        if knocked_out:
            color = COLOR_GREEN
        elif not full_window:
            color = COLOR_GRAY
        else:
            # 走到这里说明没敲出，且走完了完整周期
            if knocked_in:
                if end_price > A_price:
                    color = COLOR_YELLOW
                else:
                    color = COLOR_RED
            else:
                color = COLOR_BLUE

        results.append({
            "index": i,
            "date": dates[i],
            "price": A_price,
            "color": color,
            "ko_month": ko_month,
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
