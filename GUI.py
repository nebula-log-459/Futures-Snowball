# -*- coding: utf-8 -*-
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timedelta
import threading
import queue
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.collections import LineCollection

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

try:
    from tkcalendar import DateEntry
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False

from contracts import ContractManager
from db import FuturesDB
from crawler import FuturesCrawler
from snowball import compute_snowball
from snowball_debug import export_detail_csv

COLOR_MAP = {"green": "#2e7d32", "yellow": "#ffc000", "red": "#ff0000", "blue": "#0070c0", "gray": "#a6a6a6"}
LEGEND_LABELS = {
    "green":  "敲出",          # 发生敲出（无论是否敲入）
    "yellow": "敲入未敲出(高于期初)",  # 期末 > 期初
    "red":    "敲入未敲出(低于期初)",  # 期末 <= 期初
    "blue":   "未敲入未敲出",
    "gray":   "数据不足",
}
LEGEND_ORDER = ["green", "yellow", "red", "blue", "gray"]
PIE_ORDER = ["green", "yellow", "red", "blue"]

# 预设（时长已改为周）
PRESETS = {
    "标准型 (103/90/13周)":   (103, 90, 13, 0),
    "保守型 (102/80/26周)":   (102, 80, 26, 0),
    "激进型 (105/70/52周)":   (105, 70, 52, 0),
    "短线 (103/95/4周)":     (103, 95, 4, 0),
}

class FuturesApp:
    def __init__(self, root):
        self.root = root
        self.root.title("期货雪球策略分析系统")
        self.root.geometry("1360x860")

        self.contract_mgr = ContractManager()
        self.db = FuturesDB()
        self.crawler = FuturesCrawler(self.db)
        self.result_queue = queue.Queue()

        self._drag_start_x = None
        self._drag_start_xlim = None
        self._full_xlim = None
        self._full_ylim = None
        self._is_running = False
        self._date_manually_changed = False

        self._build_ui()
        self._load_contracts_async()
        self._poll_queue()

    def _build_ui(self):
        bottom = tk.Frame(self.root)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.progress_var = tk.StringVar(value="就绪")
        self.progress_label = tk.Label(bottom, textvariable=self.progress_var, relief=tk.SUNKEN, anchor="center", width=20, fg="#1f3864", bg="#d9e2f3", font=("Arial", 10, "bold"))
        self.progress_label.pack(side=tk.RIGHT, fill=tk.Y)

        self.status_var = tk.StringVar(value="正在加载合约列表...")
        ttk.Label(bottom, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        top = tk.Frame(self.root, bg="#e8eef7", height=48)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)

        tk.Label(top, text="交易所", bg="#e8eef7").pack(side=tk.LEFT, padx=(12, 4))
        self.exchange_var = tk.StringVar()
        self.exchange_cb = ttk.Combobox(top, textvariable=self.exchange_var, state="readonly", width=16)
        self.exchange_cb.pack(side=tk.LEFT, padx=(0, 10))
        self.exchange_cb.bind("<<ComboboxSelected>>", self._on_exchange_change)

        tk.Label(top, text="品种", bg="#e8eef7").pack(side=tk.LEFT, padx=(0, 4))
        self.variety_var = tk.StringVar()
        self.variety_cb = ttk.Combobox(top, textvariable=self.variety_var, state="readonly", width=14)
        self.variety_cb.pack(side=tk.LEFT, padx=(0, 10))
        self.variety_cb.bind("<<ComboboxSelected>>", self._on_variety_change)

        tk.Label(top, text="合约", bg="#e8eef7").pack(side=tk.LEFT, padx=(0, 4))
        self.contract_var = tk.StringVar()
        self.contract_cb = ttk.Combobox(top, textvariable=self.contract_var, state="readonly", width=10)
        self.contract_cb.pack(side=tk.LEFT, padx=(0, 10))
        self.contract_cb.bind("<<ComboboxSelected>>", self._on_contract_change)

        # ---- 初始化日期 ----
        tk.Label(top, text="起始", bg="#e8eef7").pack(side=tk.LEFT, padx=(0, 4))
        # 默认开始时间改为 2021-01-01
        self.start_var = tk.StringVar(value="2021-01-01")
        self.start_entry = ttk.Entry(top, textvariable=self.start_var, width=10)
        self.start_entry.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(top, text="结束", bg="#e8eef7").pack(side=tk.LEFT, padx=(0, 4))
        # 默认结束时间为今天
        self.end_var = tk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        self.end_entry = ttk.Entry(top, textvariable=self.end_var, width=10)
        self.end_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.db_range_var = tk.StringVar(value="已有: —")
        tk.Label(top, textvariable=self.db_range_var, bg="#e8eef7", fg="#2f5597", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(4, 0))

        main = tk.Frame(self.root)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = tk.Frame(main, width=230, bg="#f5f7fa")
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 4), pady=6)
        left.pack_propagate(False)

        tk.Label(left, text="雪球策略设置", bg="#f5f7fa", font=("Arial", 12, "bold")).pack(pady=(10, 10))
        # 预设
        row0 = tk.Frame(left, bg="#f5f7fa")
        row0.pack(fill=tk.X, padx=12, pady=(0, 6))
        tk.Label(row0, text="预设", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value="自定义")
        self.preset_cb = ttk.Combobox(row0, textvariable=self.preset_var, state="readonly", width=18, values=["自定义"] + list(PRESETS.keys()))
        self.preset_cb.pack(side=tk.LEFT)
        self.preset_cb.bind("<<ComboboxSelected>>", self._on_preset_change)

        # 敲出
        row1 = tk.Frame(left, bg="#f5f7fa")
        row1.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row1, text="敲出(%)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.out_pct_var = tk.StringVar(value="103")
        ttk.Entry(row1, textvariable=self.out_pct_var, width=6).pack(side=tk.LEFT)
        tk.Label(row1, text="≥100", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.out_pct_var.trace_add("write", self._on_param_edit)

        # 敲入
        row2 = tk.Frame(left, bg="#f5f7fa")
        row2.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row2, text="敲入(%)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.in_pct_var = tk.StringVar(value="90")
        ttk.Entry(row2, textvariable=self.in_pct_var, width=6).pack(side=tk.LEFT)
        tk.Label(row2, text="≤100", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.in_pct_var.trace_add("write", self._on_param_edit)

        # 时长
        row3 = tk.Frame(left, bg="#f5f7fa")
        row3.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row3, text="时长(周)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.duration_var = tk.StringVar(value="13")
        ttk.Entry(row3, textvariable=self.duration_var, width=6).pack(side=tk.LEFT)
        tk.Label(row3, text="整数≥1", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.duration_var.trace_add("write", self._on_param_edit)

        # 锁定期
        row4 = tk.Frame(left, bg="#f5f7fa")
        row4.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row4, text="锁定期(周)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.lockup_var = tk.StringVar(value="0")
        ttk.Entry(row4, textvariable=self.lockup_var, width=6).pack(side=tk.LEFT)
        tk.Label(row4, text="整数≥0", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.lockup_var.trace_add("write", self._on_param_edit)

        # ===== 观察日设定 =====
        # 敲入观察
        row_ki = tk.Frame(left, bg="#f5f7fa")
        row_ki.pack(fill=tk.X, padx=12, pady=(8, 0))
        tk.Label(row_ki, text="敲入观察", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.ki_freq_type = tk.StringVar(value="每天")
        self.ki_type_cb = ttk.Combobox(row_ki, textvariable=self.ki_freq_type, state="readonly", width=6, values=["每天", "每周", "每月"])
        self.ki_type_cb.pack(side=tk.LEFT)
        self.ki_type_cb.bind("<<ComboboxSelected>>", self._on_freq_change)
        self.ki_val_var = tk.StringVar(value="一")
        self.ki_val_cb = ttk.Combobox(row_ki, textvariable=self.ki_val_var, state="readonly", width=5)
        self.ki_val_cb.pack(side=tk.LEFT, padx=2)
        self.ki_val_cb.bind("<<ComboboxSelected>>", self._on_param_edit)

        # 敲出观察
        row_ko = tk.Frame(left, bg="#f5f7fa")
        row_ko.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row_ko, text="敲出观察", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.ko_freq_type = tk.StringVar(value="每周")
        self.ko_type_cb = ttk.Combobox(row_ko, textvariable=self.ko_freq_type, state="readonly", width=6, values=["每天", "每周", "每月"])
        self.ko_type_cb.pack(side=tk.LEFT)
        self.ko_type_cb.bind("<<ComboboxSelected>>", self._on_freq_change)
        self.ko_val_var = tk.StringVar(value="一")
        self.ko_val_cb = ttk.Combobox(row_ko, textvariable=self.ko_val_var, state="readonly", width=5)
        self.ko_val_cb.pack(side=tk.LEFT, padx=2)
        self.ko_val_cb.bind("<<ComboboxSelected>>", self._on_param_edit)

        self._on_freq_change() # 初始化下拉内容

        # ====== 数据统计卡片 ======
        stats_frame = tk.Frame(left, bg="#ffffff", highlightthickness=1, highlightbackground="#dcdcdc")
        stats_frame.pack(fill=tk.X, padx=12, pady=(15, 10))

        self.stats_ko_var = tk.StringVar(value="敲出率: —")
        tk.Label(stats_frame, textvariable=self.stats_ko_var, bg="#ffffff", fg="#2e7d32", font=("Arial", 11, "bold")).pack(pady=(8, 2))

        self.stats_ki_var = tk.StringVar(value="未敲入率: —")
        tk.Label(stats_frame, textvariable=self.stats_ki_var, bg="#ffffff", fg="#0070c0", font=("Arial", 11, "bold")).pack(pady=(0, 8))
        
        # 按钮
        self.detail_btn = tk.Button(left, text="生成明细 CSV", bg="#4b8b3b", fg="#ffffff", activebackground="#356628", activeforeground="#ffffff", disabledforeground="#cccccc", font=("Arial", 10), relief=tk.RAISED, bd=2, command=self._on_export_detail)
        self.detail_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(6, 0), ipady=4)

        self.run_btn = tk.Button(left, text="运 行", bg="#1f3864", fg="#ffffff", activebackground="#0f1f3a", activeforeground="#ffffff", disabledforeground="#999999", font=("Arial", 12, "bold"), relief=tk.RAISED, bd=2, command=self._on_run)
        self.run_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(8, 16), ipady=6)

        right = tk.Frame(main)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 8), pady=6)

        chart1 = ttk.LabelFrame(right, text="日线折线图", padding=3)
        chart1.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 3))
        ctrl_bar = tk.Frame(chart1, bg="#f5f7fa")
        ctrl_bar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(ctrl_bar, text="滚轮/➕➖ 缩放 · 左键拖动平移", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        tk.Button(ctrl_bar, text="＋", width=3, font=("Arial", 10, "bold"), command=lambda: self._zoom(1.25)).pack(side=tk.RIGHT, padx=1)
        tk.Button(ctrl_bar, text="－", width=3, font=("Arial", 10, "bold"), command=lambda: self._zoom(0.8)).pack(side=tk.RIGHT, padx=1)
        tk.Button(ctrl_bar, text="重置", width=5, command=self._reset_zoom).pack(side=tk.RIGHT, padx=3)

        chart_container = tk.Frame(chart1, bg="white")
        chart_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.fig1 = Figure(figsize=(8, 3.8), dpi=100)
        self.ax1 = self.fig1.add_subplot(111)
        self.ax1.set_title("等待运行...")
        self.ax1.grid(True, linestyle="--", alpha=0.4)
        self.canvas1 = FigureCanvasTkAgg(self.fig1, master=chart_container)
        self.canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        overlay = tk.Frame(self.canvas1.get_tk_widget(), bg="white", highlightthickness=1, highlightbackground="#cccccc")
        overlay.place(relx=1.0, rely=1.0, anchor="se", x=-6, y=-6)
        self.coord_var = tk.StringVar(value="—")
        tk.Label(overlay, textvariable=self.coord_var, bg="white", font=("Consolas", 9), padx=5, pady=1).pack(side=tk.LEFT)
        tk.Button(overlay, text="💾", command=self._save_chart1, bg="#f0f0f0", relief=tk.FLAT, font=("Arial", 9), padx=4).pack(side=tk.LEFT, padx=(3, 2), pady=2)
        self.canvas1.mpl_connect('scroll_event', self._on_scroll)
        self.canvas1.mpl_connect('button_press_event', self._on_press)
        self.canvas1.mpl_connect('button_release_event', self._on_release)
        self.canvas1.mpl_connect('motion_notify_event', self._on_motion)

        bottom_row = tk.Frame(right)
        bottom_row.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(3, 0))
        chart2 = ttk.LabelFrame(bottom_row, text="敲出月份柱状图", padding=3)
        chart2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        self.fig2 = Figure(figsize=(5, 2.3), dpi=100)
        self.ax2 = self.fig2.add_subplot(111)
        self.ax2.set_title("等待运行...")
        self.ax2.grid(True, linestyle="--", alpha=0.4)
        self.canvas2 = FigureCanvasTkAgg(self.fig2, master=chart2)
        self.canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        chart3 = ttk.LabelFrame(bottom_row, text="情况分布图", padding=3)
        chart3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.fig3 = Figure(figsize=(4, 2.3), dpi=100)
        self.ax3 = self.fig3.add_subplot(111)
        self.ax3.set_title("等待运行...")
        self.canvas3 = FigureCanvasTkAgg(self.fig3, master=chart3)
        self.canvas3.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _on_freq_change(self, event=None):
        # 更新敲入的选项
        if self.ki_freq_type.get() == "每周":
            self.ki_val_cb.config(values=["一", "二", "三", "四", "五"], state="readonly")
            self.ki_val_var.set("一")
        elif self.ki_freq_type.get() == "每月":
            self.ki_val_cb.config(values=["1", "2", "3"], state="readonly")
            self.ki_val_var.set("1")
        else:
            self.ki_val_cb.config(values=[], state="disabled")
            self.ki_val_var.set("")
        
        # 更新敲出的选项
        if self.ko_freq_type.get() == "每周":
            self.ko_val_cb.config(values=["一", "二", "三", "四", "五"], state="readonly")
            self.ko_val_var.set("一")
        elif self.ko_freq_type.get() == "每月":
            self.ko_val_cb.config(values=["1", "2", "3"], state="readonly")
            self.ko_val_var.set("1")
        else:
            self.ko_val_cb.config(values=[], state="disabled")
            self.ko_val_var.set("")
        self._on_param_edit()

    def _get_freq_tuple(self, type_str, val_str):
        if type_str == "每天": return ("daily", None)
        if type_str == "每周":
            mapping = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4}
            return ("weekly", mapping.get(val_str, 0))
        if type_str == "每月": return ("monthly", int(val_str))
        return ("daily", None)

    def _on_preset_change(self, event=None):
        name = self.preset_var.get()
        if name == "自定义": return
        preset = PRESETS.get(name)
        if not preset: return
        out_pct, in_pct, duration, lockup = preset
        self.preset_var.set(name)
        self.out_pct_var.set(str(out_pct))
        self.in_pct_var.set(str(in_pct))
        self.duration_var.set(str(duration))
        self.lockup_var.set(str(lockup))

    def _on_param_edit(self, *args):
        if self.preset_var.get() != "自定义":
            self.preset_var.set("自定义")

    def _load_contracts_async(self):
        def work():
            try:
                self.contract_mgr.load()
                self.result_queue.put(("contracts_ready", None))
            except Exception as e:
                self.result_queue.put(("error", f"合约列表加载失败: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _on_exchange_change(self, event=None):
        ex_code = self.contract_mgr.exchange_code(self.exchange_var.get())
        varieties = self.contract_mgr.get_varieties(ex_code)
        self.variety_cb["values"] = varieties
        if varieties: self.variety_cb.current(0); self._on_variety_change()

    def _on_variety_change(self, event=None):
        ex_code = self.contract_mgr.exchange_code(self.exchange_var.get())
        contracts = self.contract_mgr.get_contracts(ex_code, self.variety_var.get())
        display = [c.upper() for c in contracts]
        self.contract_cb["values"] = display
        if display: self.contract_cb.current(0); self._on_contract_change()

    def _set_date_range(self, start, end):
        """由代码自动设置日期时，不触发用户的修改标记"""
        self._updating_date = True  # 加锁
        self.start_var.set(start)
        self.end_var.set(end)
        self._updating_date = False # 解锁

    def _get_dates(self):
        return self.start_var.get().strip(), self.end_var.get().strip()

    def _on_contract_change(self, event=None):
        symbol_upper = self.contract_var.get().strip()
        if not symbol_upper:
            return
        
        if not hasattr(self, 'strategy_contract'):
            return
        
        self.strategy_contract.set(symbol_upper)
        symbol = symbol_upper.lower()
        first = self.db.get_first_date(symbol)
        last = self.db.get_last_date(symbol)

        if first and last:
            self.db_range_var.set(f"已有: {first} ~ {last}")
            
            # 如果用户手动改过日期，就不动它，只检查越界
            if self._date_manually_changed:
                cur_start, cur_end = self._get_dates()
                new_start = max(cur_start, first) if cur_start else first
                new_end = min(cur_end, last) if cur_end else last
                if new_start > new_end:
                    new_start, new_end = first, last
                self._set_date_range(new_start, new_end)
            else:
                # 如果用户没改过，强制为 2021-01-01 到 今天
                default_start = "2021-01-01"
                default_end = datetime.today().strftime("%Y-%m-%d")
                
                # 计算用户的默认区间和合约区间的交集
                new_start = max(default_start, first)
                new_end = min(default_end, last)
                
                # 如果该品种完全在2021年之前退市，或者起点晚于今天，强制用它的真实范围
                if new_start > new_end:
                    new_start, new_end = first, last
                    
                self._set_date_range(new_start, new_end)
        else:
            self.db_range_var.set("已有: 无缓存")

    def _validate_params(self):
        symbol = self.contract_var.get().strip().lower()
        if not symbol: self.status_var.set("请先选择合约"); return None
        start, end = self._get_dates()
        try:
            out_pct = float(self.out_pct_var.get())
            in_pct = float(self.in_pct_var.get())
            dur = int(self.duration_var.get())
            lockup = int(self.lockup_var.get())
        except ValueError:
            self.status_var.set("参数格式错误"); return None

        if not (in_pct <= 100 <= out_pct):
            self.status_var.set("参数错误: 敲入 ≤ 100 ≤ 敲出"); return None
        if dur <= 0: self.status_var.set("时长必须 ≥ 1"); return None
        if lockup < 0: self.status_var.set("锁定期必须 ≥ 0"); return None
        if start > end: self.status_var.set("日期错误"); return None

        ki_freq = self._get_freq_tuple(self.ki_freq_type.get(), self.ki_val_var.get())
        ko_freq = self._get_freq_tuple(self.ko_freq_type.get(), self.ko_val_var.get())
        return symbol, start, end, out_pct, in_pct, dur, ki_freq, ko_freq, lockup

    def _on_run(self):
        if self._is_running: return
        params = self._validate_params()
        if not params: return
        symbol, start, end, out_pct, in_pct, dur, ki_freq, ko_freq, lockup = params

        self._is_running = True
        self.run_btn.config(state="disabled")
        self.detail_btn.config(state="disabled")
        self.status_var.set(f"正在处理 {symbol} ...")
        self.progress_var.set("正在查询")

        def work():
            try:
                self.result_queue.put(("progress", "正在查询"))
                first, last = self.db.get_first_date(symbol), self.db.get_last_date(symbol)
                need_crawl = (first is None) or (first > start) or (last and last < end)
                if need_crawl:
                    self.result_queue.put(("progress", "正在爬取"))
                    self.crawler.update_symbol(symbol, verbose=False)
                    self.result_queue.put(("db_range", (self.db.get_first_date(symbol), self.db.get_last_date(symbol))))
                else:
                    self.result_queue.put(("progress", "正在导入"))

                df = self.db.load(symbol, start=start, end=end)
                if df.empty:
                    self.result_queue.put(("error", f"{symbol} 范围内无数据")); return

                actual_start, actual_end = df["date"].iloc[0], df["date"].iloc[-1]
                self.result_queue.put(("progress", "正在计算"))
                results = compute_snowball(df["date"], df["close"], out_pct, in_pct, dur, ki_freq, ko_freq, lockup)

                self.result_queue.put(("result", {
                    "symbol": symbol, "df": df, "results": results,
                    "params": {"out_pct": out_pct, "in_pct": in_pct, "duration": dur, "ki_freq": ki_freq, "ko_freq": ko_freq, "lockup": lockup},
                    "actual_range": (actual_start, actual_end), "requested_range": (start, end),
                }))
            except Exception as e:
                import traceback; traceback.print_exc(); self.result_queue.put(("error", f"处理失败: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def _on_export_detail(self):
        if self._is_running: return
        params = self._validate_params()
        if not params: return
        symbol, start, end, out_pct, in_pct, dur, ki_freq, ko_freq, lockup = params

        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{symbol}_detail.csv", filetypes=[("CSV 文件", "*.csv")])
        if not path: return
        path_sum, path_det = f"{path[:-4]}_summary.csv", f"{path[:-4]}_detail.csv"

        self._is_running = True
        self.run_btn.config(state="disabled")
        self.detail_btn.config(state="disabled")
        self.status_var.set(f"正在生成明细...")
        self.progress_var.set("正在读数据")

        def work():
            try:
                df = self.db.load(symbol, start=start, end=end)
                if df.empty: self.result_queue.put(("error", "无数据")); return
                self.result_queue.put(("progress", "正在逐点判定"))
                info = export_detail_csv(df, out_pct, in_pct, dur, ki_freq, ko_freq, lockup, path_sum, path_det,
                                         lambda c, t: self.result_queue.put(("progress", f"判定 {c}/{t}")))
                self.result_queue.put(("detail_done", info))
            except Exception as e:
                import traceback; traceback.print_exc(); self.result_queue.put(("error", f"失败: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self.result_queue.get_nowait()
                if msg_type == "contracts_ready":
                    exs = self.contract_mgr.get_exchanges()
                    self.exchange_cb["values"] = exs
                    if exs: self.exchange_cb.current(0); self._on_exchange_change()
                    self.status_var.set("合约列表就绪"); self.progress_var.set("就绪")
                elif msg_type == "progress": self.progress_var.set(payload)
                elif msg_type == "db_range":
                    first, last = payload
                    if first and last: self.db_range_var.set(f"已有: {first} ~ {last}"); self._set_date_range(first, last)
                elif msg_type == "error":
                    self.status_var.set(f"错误: {payload}"); self.progress_var.set("错误")
                    self._is_running = False; self.run_btn.config(state="normal"); self.detail_btn.config(state="normal")
                elif msg_type == "result":
                    self.progress_var.set("正在绘图"); self.root.update_idletasks()
                    self._handle_result(payload); self.progress_var.set("完成 ✓")
                    self._is_running = False; self.run_btn.config(state="normal"); self.detail_btn.config(state="normal")
                elif msg_type == "detail_done":
                    self.progress_var.set("已导出"); self.status_var.set(f"明细已导出: {payload['n_summary']} 行")
                    self._is_running = False; self.run_btn.config(state="normal"); self.detail_btn.config(state="normal")
                    messagebox.showinfo("成功", f"已生成:\n{payload['path_summary']}\n{payload['path_detail']}")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_result(self, payload):
        symbol, df, results, params, actual_range, requested_range = payload["symbol"], payload["df"], payload["results"], payload["params"], payload["actual_range"], payload["requested_range"]
        c = Counter(r["color"] for r in results)
        self._draw_chart1(df, results)
        self._draw_chart2(results)
        self._draw_chart3(c)
        
        # 计算并更新左侧指标（剔除灰色数据，与扇形图口径保持一致）
        total = len(results)
        green_v = c.get("green", 0)
        blue_v = c.get("blue", 0)
        
        # 剔除灰色后的有效判定总数
        valid_total = total - c.get("gray", 0)

        if valid_total > 0:
            # 敲出率 = 绿色 / 有效总数
            ko_rate = green_v / valid_total * 100
            # 未敲入率 = (绿色 + 蓝色) / 有效总数
            no_ki_rate = (green_v + blue_v) / valid_total * 100
            
            self.stats_ko_var.set(f"敲出率(绿色): \n   {green_v} / {valid_total} = {ko_rate:.1f}%")
            self.stats_ki_var.set(f"未敲入率(绿和蓝): \n   {green_v + blue_v} / {valid_total} = {no_ki_rate:.1f}%")
        else:
            self.stats_ko_var.set("敲出率(绿色): —")
            self.stats_ki_var.set("未敲入率(绿和蓝): —")

        # 更新底部状态栏（只显示观察日和数据量）
        ki_str = f"{params['ki_freq'][0]}" if params['ki_freq'][0] == 'daily' else f"{params['ki_freq'][0]}-{params['ki_freq'][1]}"
        ko_str = f"{params['ko_freq'][0]}" if params['ko_freq'][0] == 'daily' else f"{params['ko_freq'][0]}-{params['ko_freq'][1]}"
        self.status_var.set(f"完成: {symbol} | 观察: 敲入({ki_str}) 敲出({ko_str}) | 数据量: {total}")

    def _draw_chart1(self, df, results):
        self.ax1.clear()
        dt_list = pd.to_datetime(df["date"]).tolist()
        x = mdates.date2num(dt_list)
        y = df["close"].astype(float).values
        seg_colors, seg_list = [], []
        for i in range(1, len(x)):
            if (dt_list[i] - dt_list[i - 1]).days > 7: continue
            seg_list.append([(x[i - 1], y[i - 1]), (x[i], y[i])])
            seg_colors.append(COLOR_MAP.get(results[i - 1]["color"], "#cccccc"))

        if seg_list:
            self.ax1.add_collection(LineCollection(np.array(seg_list), colors=seg_colors, linewidths=1.4, zorder=2))

        self._full_xlim = (x.min(), x.max()); self.ax1.set_xlim(x.min(), x.max())
        y_min, y_max = y.min(), y.max(); margin = (y_max - y_min) * 0.05 if y_max > y_min else 1
        self._full_ylim = (y_min - margin, y_max + margin); self.ax1.set_ylim(self._full_ylim)

        for key in LEGEND_ORDER: self.ax1.plot([], [], color=COLOR_MAP[key], linewidth=2, label=LEGEND_LABELS[key])
        self.ax1.xaxis.set_major_locator(mdates.AutoDateLocator()); self.ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        self.ax1.set_title(f"日线折线图 - {self.contract_var.get()}", fontsize=11)
        self.ax1.tick_params(labelsize=9); self.ax1.grid(True, linestyle="--", alpha=0.4)
        self.ax1.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9, framealpha=0.9)
        self.fig1.subplots_adjust(left=0.08, right=0.85, top=0.92, bottom=0.18); self.canvas1.draw_idle()

    def _draw_chart2(self, results):
        self.ax2.clear()
        ko_months = [r["ko_month"] for r in results if r["ko_month"] > 0]
        if not ko_months: self.ax2.set_title("无敲出点"); self.canvas2.draw_idle(); return
        counter = Counter(ko_months); months = sorted(counter.keys()); counts = [counter[m] for m in months]
        bars = self.ax2.bar([str(m) for m in months], counts, color="#2e7d32", alpha=0.85, width=0.35)
        for bar, cnt in zip(bars, counts): self.ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts) * 0.02, str(cnt), ha="center", va="bottom", fontsize=9)
        self.ax2.set_title("敲出月份分布统计", fontsize=11); self.ax2.tick_params(labelsize=9); self.ax2.grid(True, linestyle="--", alpha=0.4, axis="y")
        self.ax2.set_xticks(range(len(months))); self.ax2.set_xticklabels([f"{m:g}月" for m in months], rotation=0, fontsize=9)
        self.fig2.subplots_adjust(left=0.10, right=0.97, top=0.88, bottom=0.22); self.canvas2.draw_idle()

    def _draw_chart3(self, counter):
        self.ax3.clear()
        values, labels, colors = [counter.get(k, 0) for k in PIE_ORDER], [LEGEND_LABELS[k] for k in PIE_ORDER], [COLOR_MAP[k] for k in PIE_ORDER]
        total = sum(values)
        if total == 0: self.ax3.set_title("无有效数据"); self.canvas3.draw_idle(); return
        filtered = [(v, l, c) for v, l, c in zip(values, labels, colors) if v > 0]
        values, labels, colors = [x[0] for x in filtered], [x[1] for x in filtered], [x[2] for x in filtered]

        wedges, _ = self.ax3.pie(values, colors=colors, startangle=90, counterclock=False, wedgeprops={"edgecolor": "white", "linewidth": 1.5}, radius=0.62, center=(-0.65, 0))
        for w, v in zip(wedges, values):
            ang = (w.theta2 + w.theta1) / 2; x, y = np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))
            self.ax3.annotate(f"{v} ({v/total*100:.1f}%)", xy=(-0.65 + x*0.62, y*0.62), xytext=(-0.65 + x*0.8, y*0.8), ha="left" if x>=0 else "right", va="center", fontsize=8, arrowprops=dict(arrowstyle="-", color="#999999", lw=0.8))

        self.ax3.legend(wedges, labels, loc="upper left", bbox_to_anchor=(0.65, 0.98), fontsize=8, frameon=False)
        self.ax3.set_aspect("equal");
        self.ax3.set_xlim(-1.35, 1.35);
        self.ax3.set_ylim(-1.0, 1.0);
        self.ax3.axis("off")
        self.fig3.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.02);
        self.canvas3.draw_idle()

    # 缩放/平移/保存等方法保持不变 (因篇幅省略，直接复制你原来 GUI 里的这段代码即可)
    def _on_scroll(self, event):
        if event.inaxes != self.ax1: return
        self._zoom_at(event.xdata, 1.2 if event.button == 'up' else 0.8)
    def _zoom(self, factor):
        self._zoom_at((self.ax1.get_xlim()[0] + self.ax1.get_xlim()[1]) / 2, factor)
    def _zoom_at(self, xcenter, factor):
        xlim = self.ax1.get_xlim(); width = xlim[1] - xlim[0]; new_width = width / factor
        relx = (xlim[1] - xcenter) / width; new_x0 = xcenter - new_width * (1 - relx); new_x1 = xcenter + new_width * relx
        if self._full_xlim: new_x0 = max(new_x0, self._full_xlim[0]); new_x1 = min(new_x1, self._full_xlim[1])
        self.ax1.set_xlim(new_x0, new_x1); self.canvas1.draw_idle()
    def _reset_zoom(self):
        if self._full_xlim: self.ax1.set_xlim(self._full_xlim)
        if self._full_ylim: self.ax1.set_ylim(self._full_ylim)
        self.canvas1.draw_idle()
    def _on_press(self, event):
        if event.inaxes == self.ax1 and event.button == 1:
            self._drag_start_x = event.xdata; self._drag_start_xlim = self.ax1.get_xlim(); self.canvas1.get_tk_widget().config(cursor="fleur")
    def _on_release(self, event):
        self._drag_start_x = None
        try: self.canvas1.get_tk_widget().config(cursor="")
        except: pass
    def _on_motion(self, event):
        if self._drag_start_x is not None and event.inaxes == self.ax1 and event.xdata is not None:
            dx = self._drag_start_x - event.xdata; x0, x1 = self._drag_start_xlim; nx0, nx1 = x0 + dx, x1 + dx
            if self._full_xlim:
                if nx0 < self._full_xlim[0]: nx0, nx1 = self._full_xlim[0], self._full_xlim[0] + (x1-x0)
                if nx1 > self._full_xlim[1]: nx0, nx1 = self._full_xlim[1] - (x1-x0), self._full_xlim[1]
            self.ax1.set_xlim(nx0, nx1); self.canvas1.draw_idle()
        if event.inaxes == self.ax1 and event.xdata is not None and event.ydata is not None:
            try: self.coord_var.set(f"{mdates.num2date(event.xdata).strftime('%Y-%m-%d')} {event.ydata:,.2f}")
            except: pass
        else: self.coord_var.set("—")
    def _save_chart1(self):
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile=f"{self.contract_var.get() or 'chart'}.png")
        if path:
            try: self.fig1.savefig(path, dpi=300, bbox_inches="tight"); self.status_var.set(f"已保存: {path}")
            except Exception as e: self.status_var.set(f"保存失败: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FuturesApp(root)
    root.mainloop()
