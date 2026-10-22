# -*- coding: utf-8 -*-
"""
合约列表管理层
- 从六个交易所 futures_contract_info_* 接口拉取全部期货合约
- 从 futures_display_main_sina 拉取主连，并对 DCE/GFEX 进行日线接口探测兜底
- 组织成 交易所 → 品种 → [合约代码] 三级结构
- 缓存为 JSON，有效期 7 天
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
import akshare as ak


# ==================== 配置 ====================
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_FILE = CACHE_DIR / "contracts.json"
MAX_AGE_DAYS = 7

EXCHANGE_NAMES = {
    "shfe":  "上海期货交易所",
    "dce":   "大连商品交易所",
    "czce":  "郑州商品交易所",
    "cffex": "中国金融期货交易所",
    "ine":   "上海国际能源交易中心",
    "gfex":  "广州期货交易所",
}

FALLBACK_NAMES = {
    "cu": "沪铜", "al": "沪铝", "zn": "沪锌", "pb": "沪铅", "ni": "沪镍",
    "sn": "沪锡", "au": "沪金", "ag": "沪银", "rb": "螺纹钢", "hc": "热卷",
    "ss": "不锈钢", "wr": "线材", "ru": "天然橡胶", "bu": "沥青", "fu": "燃油",
    "sp": "纸浆", "ao": "氧化铝", "br": "丁二烯橡胶", "op": "胶版印刷纸",
    "ad": "铸造铝合金",
    "sc": "上海原油", "lu": "低硫燃料油", "nr": "20号胶", "bc": "国际铜", "ec": "集运指数欧线期货",
    "a": "豆一", "b": "豆二", "m": "豆粕", "y": "豆油", "p": "棕榈油",
    "c": "玉米", "cs": "淀粉", "jd": "鸡蛋", "lh": "生猪", "i": "铁矿石",
    "j": "焦炭", "jm": "焦煤", "l": "塑料", "v": "PVC", "pp": "聚丙烯",
    "eg": "乙二醇", "eb": "苯乙烯", "pg": "液化石油气", "rr": "粳米", "lg": "原木",
    "sr": "白糖", "cf": "棉花", "cy": "棉纱", "ta": "PTA", "ma": "甲醇",
    "fg": "玻璃", "sa": "纯碱", "ur": "尿素", "sf": "硅铁", "sm": "锰硅",
    "ap": "苹果", "cj": "红枣", "pk": "花生", "oi": "菜油", "rm": "菜粕",
    "pf": "短纤", "sh": "烧碱", "px": "对二甲苯", "wh": "强麦",
    "jr": "粳稻", "ri": "早籼稻", "lr": "晚籼稻", "rs": "菜籽",
    "pm": "普麦", "zc": "动力煤", "pl": "丙烯", "pr": "瓶片",
    "si": "工业硅", "lc": "碳酸锂", "ps": "多晶硅", "pt": "铂", "pd": "钯",
    "if": "沪深300", "ih": "上证50", "ic": "中证500", "im": "中证1000",
    "ts": "2年期国债", "tf": "5年期国债", "t": "10年期国债", "tl": "30年期国债",
}

# 大商所和广期所备用主连代码字典（用于日线接口探测兜底）
BACKUP_MAIN_CONTRACTS = {
    "dce": {
        "豆一主连": "A0", "豆二主连": "B0", "豆粕主连": "M0", "豆油主连": "Y0",
        "棕榈油主连": "P0", "玉米主连": "C0", "淀粉主连": "CS0", "鸡蛋主连": "JD0",
        "生猪主连": "LH0", "铁矿石主连": "I0", "焦炭主连": "J0", "焦煤主连": "JM0",
        "塑料主连": "L0", "PVC主连": "V0", "聚丙烯主连": "PP0", "乙二醇主连": "EG0",
        "苯乙烯主连": "EB0", "液化石油气主连": "PG0", "粳米主连": "RR0", "原木主连": "LG0"
    },
    "gfex": {
        "工业硅主连": "SI0", "碳酸锂主连": "LC0", "多晶硅主连": "PS0"
    }
}


# ==================== 合约管理器 ====================
class ContractManager:
    def __init__(self, cache_file=CACHE_FILE, max_age_days=MAX_AGE_DAYS):
        self.cache_file = Path(cache_file)
        self.max_age_days = max_age_days
        self.data = {}
        self.updated_at = None

    # ---------- 缓存 ----------
    def _cache_valid(self):
        if not self.cache_file.exists():
            return False
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            updated = datetime.fromisoformat(cached["updated_at"])
            if datetime.now() - updated > timedelta(days=self.max_age_days):
                return False
            self.data = cached["data"]
            self.updated_at = updated
            return True
        except Exception as e:
            print(f"[缓存读取失败] {e}")
            return False

    def _save_cache(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = datetime.now()
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "updated_at": self.updated_at.isoformat(),
                "data": self.data,
            }, f, ensure_ascii=False, indent=2)

    # ---------- 加载 ----------
    def load(self, force_refresh=False):
        if not force_refresh and self._cache_valid():
            print(f"[合约列表] 使用缓存 (更新于 {self.updated_at:%Y-%m-%d %H:%M})")
            return self.data
        print("[合约列表] 重新拉取各交易所接口...")
        self.refresh()
        return self.data

    def refresh(self):
        self.data = {}
        name_map = self._load_sina_names()

        self._fetch_shfe(name_map)
        self._fetch_dce(name_map)
        self._fetch_czce(name_map)
        self._fetch_ine(name_map)
        self._fetch_gfex(name_map)
        self._fetch_cffex(name_map)

        # 最后追加主连（包含 DCE/GFEX 的探测兜底）
        self._safe_add_main_contracts()

        self._save_cache()
        total_v = sum(len(v) for v in self.data.values())
        total_c = sum(len(c) for v in self.data.values() for c in v.values())
        print(f"[合约列表] 完成: {len(self.data)} 个交易所, "
              f"{total_v} 个品种, {total_c} 个合约")
        return self.data

    # ---------- 主连添加逻辑 ----------
    def _safe_add_main_contracts(self):
        """带安全探测的主连添加逻辑"""
        # 1. 跑原来的新浪列表逻辑
        try:
            df = ak.futures_display_main_sina()
            for _, row in df.iterrows():
                symbol = str(row["symbol"])
                exchange = str(row["exchange"]).lower()
                name = str(row["name"]).replace("连续", "").strip()
                
                if exchange not in self.data:
                    self.data[exchange] = {}
                variety_name = f"{name}主连"
                self.data[exchange].setdefault(variety_name, [])
                if symbol not in self.data[exchange][variety_name]:
                    self.data[exchange][variety_name].append(symbol)
        except Exception as e:
            print(f"[主连] 列表接口失败: {e}")

        # 2. 针对 DCE 和 GFEX，探测日线接口是否有数据，有才加入
        print("[主连] 正在探测 DCE 和 GFEX 的备用主连数据...")
        for ex, data in BACKUP_MAIN_CONTRACTS.items():
            if ex not in self.data:
                self.data[ex] = {}
            
            for name, code in data.items():
                if name in self.data[ex] and self.data[ex][name]:
                    continue
                
                try:
                    test_df = ak.futures_zh_daily_sina(symbol=code)
                    if test_df is not None and not test_df.empty:
                        self.data[ex][name] = [code]
                        # print(f"  -> 探测成功，加入 {name} ({code})")
                except Exception:
                    pass

    # ---------- 中文名映射 ----------
    @staticmethod
    def _load_sina_names():
        result = {}
        try:
            df = ak.futures_display_main_sina()
            for _, row in df.iterrows():
                symbol = str(row["symbol"]).rstrip("0").lower()
                name = str(row["name"]).replace("连续", "").strip()
                if symbol:
                    result[symbol] = name
        except Exception as e:
            print(f"[新浪中文名] 获取失败: {e}")
        return result

    def _cn_name(self, variety_code, name_map):
        code = variety_code.lower()
        return name_map.get(code) or FALLBACK_NAMES.get(code, variety_code.upper())

    # ---------- 各交易所 ----------
    @staticmethod
    def _recent_dates(n=10):
        today = datetime.today()
        return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]

    def _add(self, exchange, variety, contract, name_map):
        vcode = variety.lower()
        cn = self._cn_name(vcode, name_map)
        self.data.setdefault(exchange, {}).setdefault(cn, []).append(contract)

    @staticmethod
    def _extract_variety(contract):
        m = re.match(r"^([a-zA-Z]+)", str(contract))
        return m.group(1).lower() if m else ""

    def _fetch_shfe(self, name_map):
        INE_ONLY = {"nr", "sc", "lu", "bc", "ec"}
        for d in self._recent_dates():
            try:
                df = ak.futures_contract_info_shfe(date=d)
                if df is None or df.empty:
                    continue
                for code in df["合约代码"].astype(str):
                    v = self._extract_variety(code)
                    if v and v not in INE_ONLY:
                        self._add("shfe", v, code.lower(), name_map)
                return
            except Exception:
                continue

    def _fetch_dce(self, name_map):
        try:
            df = ak.futures_contract_info_dce()
            if df is None or df.empty:
                return
            col = "合约" if "合约" in df.columns else "合约代码"
            for code in df[col].astype(str):
                v = self._extract_variety(code)
                if v:
                    self._add("dce", v, code.lower(), name_map)
        except Exception as e:
            print(f"[DCE] 合约信息接口失败，等待主连探测兜底")

    def _fetch_czce(self, name_map):
        for d in self._recent_dates():
            try:
                df = ak.futures_contract_info_czce(date=d)
                if df is None or df.empty:
                    continue
                for code in df["合约代码"].astype(str):
                    v = self._extract_variety(code)
                    if v:
                        self._add("czce", v, code.lower(), name_map)
                return
            except Exception:
                continue

    def _fetch_ine(self, name_map):
        for d in self._recent_dates():
            try:
                df = ak.futures_contract_info_ine(date=d)
                if df is None or df.empty:
                    continue
                for code in df["合约代码"].astype(str):
                    v = self._extract_variety(code)
                    if v:
                        self._add("ine", v, code.lower(), name_map)
                return
            except Exception:
                continue

    def _fetch_gfex(self, name_map):
        try:
            df = ak.futures_contract_info_gfex()
            if df is None or df.empty:
                return
            col = "合约代码" if "合约代码" in df.columns else "合约"
            for code in df[col].astype(str):
                v = self._extract_variety(code)
                if v:
                    self._add("gfex", v, code.lower(), name_map)
        except Exception as e:
            print(f"[GFEX] 失败: {e}")

    def _fetch_cffex(self, name_map):
        for d in self._recent_dates():
            try:
                df = ak.futures_contract_info_cffex(date=d)
                if df is None or df.empty:
                    continue
                for code in df["合约代码"].astype(str):
                    if "-C-" in code or "-P-" in code:
                        continue
                    v = self._extract_variety(code)
                    if v:
                        self._add("cffex", v, code.upper(), name_map)
                return
            except Exception:
                continue

    # ---------- 对外查询 ----------
    def get_exchanges(self):
        order = ["shfe", "dce", "czce", "ine", "gfex", "cffex"]
        return [EXCHANGE_NAMES[c] for c in order if c in self.data]

    def exchange_code(self, cn_name):
        for code, name in EXCHANGE_NAMES.items():
            if name == cn_name:
                return code
        return None

    def get_varieties(self, exchange_code):
        return sorted(self.data.get(exchange_code, {}).keys())

    def get_contracts(self, exchange_code, variety_cn):
        contracts = self.data.get(exchange_code, {}).get(variety_cn, [])
        return sorted(set(contracts))

    def summary(self):
        print("\n" + "=" * 70)
        print("合约列表统计")
        print("=" * 70)
        for code in ["shfe", "dce", "czce", "ine", "gfex", "cffex"]:
            if code not in self.data:
                continue
            varieties = self.data[code]
            n_v = len(varieties)
            n_c = sum(len(c) for c in varieties.values())
            print(f"\n{EXCHANGE_NAMES[code]} ({n_v} 个品种, {n_c} 个合约)")
            for vname, contracts in sorted(varieties.items()):
                if "主连" in vname:
                    continue
                sample = ", ".join(sorted(contracts)[:6])
                suffix = "..." if len(contracts) > 6 else ""
                print(f"  {vname:8s} ({len(contracts):3d}): {sample}{suffix}")


if __name__ == "__main__":
    mgr = ContractManager()
    mgr.load(force_refresh=True)
    mgr.summary()
