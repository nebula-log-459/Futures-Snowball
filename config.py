# -*- coding: utf-8 -*-
# config.py

# 预设参数 (敲出%, 敲入%, 时长周, 锁定期周)
PRESETS = {
    "标准型 (103/90/13周)":   (103, 90, 13, 0),
    "保守型 (102/80/26周)":   (102, 80, 26, 0),
    "激进型 (105/70/52周)":   (105, 70, 52, 0),
    "短线 (103/95/4周)":     (103, 95, 4, 0),
}

def validate_params(symbol, start, end, out_pct_str, in_pct_str, dur_str, lockup_str):
    """
    纯业务逻辑的校验函数。
    返回: (is_valid, msg, parsed_data)
    """
    if not symbol:
        return False, "请先选择合约", None

    if start > end:
        return False, "日期错误：起始日期不能晚于结束日期", None

    try:
        out_pct = float(out_pct_str)
        in_pct = float(in_pct_str)
        dur = int(dur_str)
        lockup = int(lockup_str)
    except ValueError:
        return False, "参数格式错误，请输入有效的数字", None

    if not (in_pct <= 100 <= out_pct):
        return False, "参数错误: 必须满足 敲入 ≤ 100 ≤ 敲出", None
    if dur <= 0:
        return False, "时长必须 ≥ 1", None
    if lockup < 0:
        return False, "锁定期必须 ≥ 0", None
    if lockup >= dur:
        return False, "锁定期不能大于等于产品总时长", None

    # 校验通过，返回清洗后的数值字典
    parsed_data = {
        "symbol": symbol.lower(),
        "start": start,
        "end": end,
        "out_pct": out_pct,
        "in_pct": in_pct,
        "dur": dur,
        "lockup": lockup
    }
    return True, "OK", parsed_data
