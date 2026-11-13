# -*- coding: utf-8 -*-
# returns_calculator.py

def calculate_returns(results, params, ui_params):
    c_early = ui_params["c_early"] / 100.0
    c_late = ui_params["c_late"] / 100.0
    c_red = ui_params["c_red"] / 100.0
    margin = ui_params["margin"] / 100.0
    principal = ui_params["principal"]
    
    mode = ui_params.get("mode", "单一票息")
    early_unit = ui_params["early_unit"]
    early_val = ui_params["early_val"]
    
    total_weeks = params["duration"]
    total_days = total_weeks * 7

    # 计算阶段1覆盖的天数
    if early_unit == "按周":
        early_days = early_val * 7
    elif early_unit == "按月":
        early_days = early_val * 30
    else:
        early_days = early_val

    # 本金展示字符串
    principal_wan = principal / 10000.0
    p_str = f"{int(principal_wan)}万" if principal_wan.is_integer() else f"{principal_wan:.2f}万"

    # ================= 核心修复：提前算好蓝色(未敲入未敲出)的固定收益 =================
    if early_unit == "按周":
        weeks = max(1, round(total_days / 7))
        blue_amount = principal * c_red * (weeks / 52.0)
        blue_formula = f"{p_str} × {c_red*100:.2f}% × ({weeks}/52) = {int(round(blue_amount,0)):,} 元"
    elif early_unit == "按月":
        months = max(1, round(total_days / 30))
        blue_amount = principal * c_red * (months / 12.0)
        blue_formula = f"{p_str} × {c_red*100:.2f}% × ({months}/12) = {int(round(blue_amount,0)):,} 元"
    else:
        blue_amount = principal * c_red * (total_days / 360.0)
        blue_formula = f"{p_str} × {c_red*100:.2f}% × ({total_days}/360) = {int(round(blue_amount,0)):,} 元"

    stats = {
        "green": {"count": 0, "total_amount": 0.0},
        # 直接在这里赋上公式和金额，不管有没有样本都有值
        "blue": {"count": 0, "total_amount": blue_amount, "formula": blue_formula, "prob": 0.0},
        "yellow": {"count": 0, "total_amount": 0.0},
        "red": {"count": 0, "total_amount": 0.0},
        "valid_total": 0, "win_count": 0,
        "bucket_stats": {}
    }

    for r in results:
        color = r["color"]
        if color == "gray": continue
            
        stats["valid_total"] += 1
        hold_days = r.get("hold_days", 0)
        amount = 0.0 
        
        # 1. 绿色（敲出）
        if color == "green":
            if early_unit == "按周":
                unit_val = max(1, round(hold_days / 7))
                base_str = "52"
                label = f"第{unit_val}周"
                is_early = unit_val <= early_val
            elif early_unit == "按月":
                # 【修改】：既然底层是30天滚动，直接根据天数算出是第几个月
                unit_val = max(1, round(hold_days / 30))
                base_str = "12"
                label = f"第{unit_val}月"
                is_early = unit_val <= early_val
            else:
                unit_val = hold_days
                base_str = "360"
                label = f"第{unit_val}天"
                is_early = unit_val <= early_val

            current_rate = c_early if is_early else c_late
            rate_str = f"{current_rate*100:.2f}%"

            denominator = 360.0 if early_unit == "按观察日" else float(base_str)
            amount = principal * current_rate * (unit_val / denominator)
            
            amount_str = f"{int(round(amount, 0)):,} 元"
            formula = f"{p_str} × {rate_str} × ({unit_val}/{base_str}) = {amount_str}"

            stats["win_count"] += 1 
            stats["green"]["total_amount"] += amount

            if label not in stats["bucket_stats"]:
                stats["bucket_stats"][label] = {"count": 0, "sort_key": unit_val, "formula": formula}
            
            stats["bucket_stats"][label]["count"] += 1

        # 2. 蓝色（未敲入未敲出）
        elif color == "blue":
            stats["win_count"] += 1
            # 钱和公式已经在循环开始前算好了，这里不用再算

        # 3. 黄色（没钱）
        elif color == "yellow":
            pass
            
        # 4. 红色（爆仓）
        elif color == "red":
            price_drop = 1.0 - (r.get("end_price", 0) / r["price"])
            loss_amount = - (price_drop * principal / margin)
            amount = max(-principal, loss_amount)
            stats["red"]["total_amount"] += amount

        stats[color]["count"] += 1

    if stats["valid_total"] > 0:
        stats["win_rate"] = stats["win_count"] / stats["valid_total"]
        stats["blue"]["prob"] = stats["blue"]["count"] / stats["valid_total"]
    else:
        stats["win_rate"] = 0.0

    return stats
