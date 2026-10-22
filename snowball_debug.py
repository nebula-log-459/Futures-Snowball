# -*- coding: utf-8 -*-
"""
雪球判定过程诊断（与 snowball.py 逻辑严格同步）
"""
import math
from dateutil.relativedelta import relativedelta
import pandas as pd

COLOR_GREEN  = "green"
COLOR_YELLOW = "yellow"
COLOR_RED    = "red"
COLOR_BLUE   = "blue"
COLOR_GRAY   = "gray"

def _month_diff(d1, d2):
    if d2 <= d1:
        return 0
    delta = relativedelta(d2, d1)
    months = delta.years * 12 + delta.months
    days = delta.days
    total = months + days / 30.0
    rounded = math.ceil(total * 2) / 2
    return max(rounded, 0.5)


def evaluate_one_point(dt_list, prices, i, out_pct, in_pct,
                        duration_weeks, ki_freq, ko_freq, lockup_weeks):
    A_date = dt_list[i]
    A_price = float(prices[i])
    out_price = A_price * out_pct / 100.0
    in_price = A_price * in_pct / 100.0
    target_end = A_date + relativedelta(weeks=duration_weeks)
    lockup_end = A_date + relativedelta(weeks=lockup_weeks)
    last_date = dt_list[-1]
    full_window = last_date >= target_end

    knocked_in = False
    knocked_in_date = None
    knocked_in_price = None
    knocked_out = False
    ko_month = 0
    ko_date = None

    steps = []
    current_month = None
    month_day_count = 0
    end_price = None

    for j in range(i + 1, len(dt_list)):
        D_date = dt_list[j]
        
        if D_date > target_end:
            if end_price is None:
                end_price = float(prices[j - 1]) if j > i else A_price
            steps.append((j, D_date, float(prices[j]), "窗口结束", f"超出窗口 {target_end:%Y-%m-%d}"))
            break

        end_price = float(prices[j])

        if D_date.month != current_month:
            current_month = D_date.month
            month_day_count = 1
        else:
            month_day_count += 1

        P = float(prices[j])
        
        is_ko_day = False
        if D_date >= lockup_end:
            if ko_freq[0] == "daily": is_ko_day = True
            elif ko_freq[0] == "weekly" and D_date.weekday() == ko_freq[1]: is_ko_day = True
            elif ko_freq[0] == "monthly" and month_day_count == ko_freq[1]: is_ko_day = True
        else:
            steps.append((j, D_date, P, "锁定期", "未过锁定期，不判敲出"))

        is_ki_day = False
        if ki_freq[0] == "daily": is_ki_day = True
        elif ki_freq[0] == "weekly" and D_date.weekday() == ki_freq[1]: is_ki_day = True
        elif ki_freq[0] == "monthly" and month_day_count == ki_freq[1]: is_ki_day = True

        # 敲出
        if is_ko_day and P >= out_price:
            knocked_out = True
            ko_date = D_date
            ko_month = _month_diff(A_date, D_date)
            steps.append((j, D_date, P, "敲出", f"价格 {P:.2f} >= 敲出价 {out_price:.2f}"))
            break

        # 敲入
        if is_ki_day:
            if P <= in_price:
                if not knocked_in:
                    knocked_in = True
                    knocked_in_date = D_date
                    knocked_in_price = P
                    steps.append((j, D_date, P, "敲入", f"价格 {P:.2f} <= 敲入价 {in_price:.2f}"))
                else:
                    steps.append((j, D_date, P, "再次敲入", f"重置回升标记"))
            else:
                steps.append((j, D_date, P, "普通", ""))

    # 如果由于数据不够导致根本没触发过窗口结束
    if end_price is None:
        end_price = float(prices[-1])

    # 颜色判定（新逻辑）
    if knocked_out:
        color = COLOR_GREEN
    elif not full_window:
        color = COLOR_GRAY
    else:
        if knocked_in:
            if end_price > A_price:
                color = COLOR_YELLOW
            else:
                color = COLOR_RED
        else:
            color = COLOR_BLUE

    return {
        "A_index": i, "A_date": A_date.strftime("%Y-%m-%d"), "A_weekday": f"周{A_date.weekday()+1}",
        "A_price": A_price, "敲出价": round(out_price, 4), "敲入价": round(in_price, 4),
        "窗口结束": target_end.strftime("%Y-%m-%d"), "期末价": round(end_price, 4),
        "窗口走完": "是" if full_window else "否",
        "是否敲入": "是" if knocked_in else "否", "敲入日期": knocked_in_date.strftime("%Y-%m-%d") if knocked_in_date else "",
        "是否敲出": "是" if knocked_out else "否", "敲出日期": ko_date.strftime("%Y-%m-%d") if ko_date else "",
        "敲出月份": ko_month, "颜色": color, "遍历步数": len(steps), "steps": steps,
    }

def export_detail_csv(df, out_pct, in_pct, duration_weeks, ki_freq, ko_freq, lockup_weeks,
                       path_summary, path_detail, progress_cb=None):
    dt_list = [pd.to_datetime(d) for d in df["date"]]
    prices = df["close"].astype(float).tolist()
    n = len(dt_list)

    all_results = []
    for i in range(n):
        r = evaluate_one_point(dt_list, prices, i, out_pct, in_pct, duration_weeks, ki_freq, ko_freq, lockup_weeks)
        all_results.append(r)
        if progress_cb and (i % 50 == 0 or i == n - 1): progress_cb(i + 1, n)

    summary_rows = [{k: v for k, v in r.items() if k != "steps"} for r in all_results]
    pd.DataFrame(summary_rows).to_csv(path_summary, index=False, encoding="utf-8-sig")

    detail_rows = []
    for r in all_results:
        for step in r["steps"]:
            j, D_date, P, tag, desc = step
            detail_rows.append({
                "A_index": r["A_index"], "A_date": r["A_date"], "A_price": r["A_price"],
                "敲出价": r["敲出价"], "敲入价": r["敲入价"], "D_index": j,
                "D_date": D_date.strftime("%Y-%m-%d"), "D_weekday": f"周{D_date.weekday()+1}",
                "D_price": round(P, 4), "状态": tag, "说明": desc,
                "最终颜色": r["颜色"], "敲出月份": r["敲出月份"],
            })
    pd.DataFrame(detail_rows).to_csv(path_detail, index=False, encoding="utf-8-sig")

    return {"n_summary": len(summary_rows), "n_detail": len(detail_rows),
            "path_summary": path_summary, "path_detail": path_detail}
