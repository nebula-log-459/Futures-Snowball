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

from returns_window import ReturnsWindow
from contracts import ContractManager
from db import FuturesDB
from crawler import FuturesCrawler
from snowball import compute_snowball
from snowball_debug import export_detail_csv
from config import PRESETS, validate_params
from chart_utils import ChartManager

class FuturesApp:
    def __init__(self, root):
        self.root = root
        self.root.title("期货雪球策略分析系统")
        self.root.geometry("1360x860")

        self.contract_mgr = ContractManager()
        self.db = FuturesDB()
        self.crawler = FuturesCrawler(self.db)
        self.result_queue = queue.Queue()

        self._is_running = False
        
        # 用于记录是否是程序启动后的第一次选中合约
        self._is_first_load = True 

        self.chart_mgr = ChartManager(self)

        self._build_ui()

        self._set_date_range("2021-01-01", datetime.today().strftime("%Y-%m-%d"))

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

        tk.Label(top, text="起始", bg="#e8eef7").pack(side=tk.LEFT, padx=(0, 4))
        self.start_var = tk.StringVar(value="2021-01-01")
        self.start_entry = ttk.Entry(top, textvariable=self.start_var, width=10)
        self.start_entry.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(top, text="结束", bg="#e8eef7").pack(side=tk.LEFT, padx=(0, 4))
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
        row0 = tk.Frame(left, bg="#f5f7fa")
        row0.pack(fill=tk.X, padx=12, pady=(0, 6))
        tk.Label(row0, text="预设", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value="自定义")
        self.preset_cb = ttk.Combobox(row0, textvariable=self.preset_var, state="readonly", width=18, values=["自定义"] + list(PRESETS.keys()))
        self.preset_cb.pack(side=tk.LEFT)
        self.preset_cb.bind("<<ComboboxSelected>>", self._on_preset_change)

        row1 = tk.Frame(left, bg="#f5f7fa")
        row1.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row1, text="敲出(%)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.out_pct_var = tk.StringVar(value="103")
        ttk.Entry(row1, textvariable=self.out_pct_var, width=6).pack(side=tk.LEFT)
        tk.Label(row1, text="≥100", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.out_pct_var.trace_add("write", self._on_param_edit)

        row2 = tk.Frame(left, bg="#f5f7fa")
        row2.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row2, text="敲入(%)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.in_pct_var = tk.StringVar(value="90")
        ttk.Entry(row2, textvariable=self.in_pct_var, width=6).pack(side=tk.LEFT)
        tk.Label(row2, text="≤100", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.in_pct_var.trace_add("write", self._on_param_edit)

        row3 = tk.Frame(left, bg="#f5f7fa")
        row3.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row3, text="时长(周)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.duration_var = tk.StringVar(value="13")
        ttk.Entry(row3, textvariable=self.duration_var, width=6).pack(side=tk.LEFT)
        tk.Label(row3, text="整数≥1", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.duration_var.trace_add("write", self._on_param_edit)

        row4 = tk.Frame(left, bg="#f5f7fa")
        row4.pack(fill=tk.X, padx=12, pady=3)
        tk.Label(row4, text="锁定期(周)", bg="#f5f7fa", width=7, anchor="w").pack(side=tk.LEFT)
        self.lockup_var = tk.StringVar(value="0")
        ttk.Entry(row4, textvariable=self.lockup_var, width=6).pack(side=tk.LEFT)
        tk.Label(row4, text="整数≥0", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        self.lockup_var.trace_add("write", self._on_param_edit)

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

        self._on_freq_change()

        stats_frame = tk.Frame(left, bg="#ffffff", highlightthickness=1, highlightbackground="#dcdcdc")
        stats_frame.pack(fill=tk.X, padx=12, pady=(15, 10))

        self.stats_ko_var = tk.StringVar(value="敲出率: —")
        tk.Label(stats_frame, textvariable=self.stats_ko_var, bg="#ffffff", fg="#2e7d32", font=("Arial", 11, "bold")).pack(pady=(8, 2))

        self.stats_ki_var = tk.StringVar(value="未敲入率: —")
        tk.Label(stats_frame, textvariable=self.stats_ki_var, bg="#ffffff", fg="#0070c0", font=("Arial", 11, "bold")).pack(pady=(0, 8))
        
        self.detail_btn = tk.Button(left, text="生成明细 CSV", bg="#4b8b3b", fg="#ffffff", activebackground="#356628", activeforeground="#ffffff", disabledforeground="#cccccc", font=("Arial", 10), relief=tk.RAISED, bd=2, command=self._on_export_detail)
        self.detail_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(6, 0), ipady=4)

        self.run_btn = tk.Button(left, text="运 行", bg="#1f3864", fg="#ffffff", activebackground="#0f1f3a", activeforeground="#ffffff", disabledforeground="#999999", font=("Arial", 12, "bold"), relief=tk.RAISED, bd=2, command=self._on_run)
        self.run_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(8, 16), ipady=6)

        self.return_btn = tk.Button(left, text="收益率测算", bg="#c65911", fg="#ffffff", font=("Arial", 10, "bold"), command=self._open_returns_window)
        self.return_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(6, 0), ipady=4)

        right = tk.Frame(main)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 8), pady=6)

        chart1 = ttk.LabelFrame(right, text="日线折线图", padding=3)
        chart1.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 3))
        ctrl_bar = tk.Frame(chart1, bg="#f5f7fa")
        ctrl_bar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(ctrl_bar, text="滚轮/➕➖ 缩放 · 左键拖动平移", bg="#f5f7fa", fg="#888", font=("Arial", 8)).pack(side=tk.LEFT, padx=4)
        
        tk.Button(ctrl_bar, text="＋", width=3, font=("Arial", 10, "bold"), command=lambda: self.chart_mgr.zoom(1.25)).pack(side=tk.RIGHT, padx=1)
        tk.Button(ctrl_bar, text="－", width=3, font=("Arial", 10, "bold"), command=lambda: self.chart_mgr.zoom(0.8)).pack(side=tk.RIGHT, padx=1)
        tk.Button(ctrl_bar, text="重置", width=5, command=self.chart_mgr.reset_zoom).pack(side=tk.RIGHT, padx=3)

        # ================= 辅助线控制区 =================
        # 日期输入框
        tk.Label(ctrl_bar, text="辅助线日期:", bg="#f5f7fa", font=("Arial", 9)).pack(side=tk.LEFT, padx=(15, 2))
        self.guide_date_var = tk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        self.guide_date_entry = ttk.Entry(ctrl_bar, textvariable=self.guide_date_var, width=11)
        self.guide_date_entry.pack(side=tk.LEFT)
        
        # 勾选框
        self.show_guide_var = tk.BooleanVar(value=False)
        self.guide_check = tk.Checkbutton(ctrl_bar, text="显示辅助线", variable=self.show_guide_var, 
                                          bg="#f5f7fa", activebackground="#f5f7fa",
                                          command=self.chart_mgr.toggle_guide_lines)
        self.guide_check.pack(side=tk.LEFT, padx=5)
        # ========================================================

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
        
        tk.Button(overlay, text="💾", command=lambda: self.chart_mgr.save_chart1(self.contract_var.get()), bg="#f0f0f0", relief=tk.FLAT, font=("Arial", 9), padx=4).pack(side=tk.LEFT, padx=(3, 2), pady=2)

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

        # 此时 canvas 全部创建好了，绑定事件
        self.canvas1.mpl_connect('scroll_event', self.chart_mgr.on_scroll)
        self.canvas1.mpl_connect('button_press_event', self.chart_mgr.on_press)
        self.canvas1.mpl_connect('button_release_event', self.chart_mgr.on_release)
        self.canvas1.mpl_connect('motion_notify_event', self.chart_mgr.on_motion)

    def _on_freq_change(self, event=None):
        if self.ki_freq_type.get() == "每周":
            self.ki_val_cb.config(values=["一", "二", "三", "四", "五"], state="readonly")
            self.ki_val_var.set("一")
        else:
            # 【修改】只要不是“每周”，后面的框统统清空并禁用（包括每天和每月）
            self.ki_val_cb.config(values=[], state="disabled")
            self.ki_val_var.set("")
        
        if self.ko_freq_type.get() == "每周":
            self.ko_val_cb.config(values=["一", "二", "三", "四", "五"], state="readonly")
            self.ko_val_var.set("一")
        else:
            # 【修改】同上
            self.ko_val_cb.config(values=[], state="disabled")
            self.ko_val_var.set("")
            
        self._on_param_edit()

    def _get_freq_tuple(self, type_str, val_str):
        if type_str == "每天": return ("daily", None)
        if type_str == "每周":
            mapping = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4}
            return ("weekly", mapping.get(val_str, 0))
        if type_str == "每月": return ("monthly", 1)
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
        """专门用于安全地修改 UI 日期，不会被当成用户手动输入"""
        self._updating_date = True
        self.start_var.set(start)
        self.end_var.set(end)
        self._updating_date = False

    def _get_dates(self):
        return self.start_var.get().strip(), self.end_var.get().strip()
    
    def _on_contract_change(self, event=None):
        """切换合约时的时间对齐逻辑"""
        symbol_upper = self.contract_var.get().strip()
        if not symbol_upper:
            return
        
        symbol = symbol_upper.lower()
        first = self.db.get_first_date(symbol)
        last = self.db.get_last_date(symbol)

        if first and last:
            self.db_range_var.set(f"已有: {first} ~ {last}")
            
            if self._is_first_load:
                self._is_first_load = False
                default_start = "2021-01-01"
                default_end = datetime.today().strftime("%Y-%m-%d")
                new_start = max(default_start, first)
                new_end = min(default_end, last)
                if new_start > new_end:
                    new_start, new_end = first, last
                self._set_date_range(new_start, new_end)
            else:
                cur_start, cur_end = self._get_dates()
                new_start = max(cur_start, first) if cur_start else first
                new_end = min(cur_end, last) if cur_end else last
                if new_start > new_end:
                    new_start, new_end = first, last
                self._set_date_range(new_start, new_end)
        else:
            self.db_range_var.set("已有: 无缓存")
            
    def _validate_params(self):
        symbol = self.contract_var.get().strip()
        start, end = self._get_dates()
        
        out_pct_str = self.out_pct_var.get()
        in_pct_str = self.in_pct_var.get()
        dur_str = self.duration_var.get()
        lockup_str = self.lockup_var.get()
        
        ki_freq = self._get_freq_tuple(self.ki_freq_type.get(), self.ki_val_var.get())
        ko_freq = self._get_freq_tuple(self.ko_freq_type.get(), self.ko_val_var.get())

        is_valid, msg, parsed = validate_params(symbol, start, end, out_pct_str, in_pct_str, dur_str, lockup_str)
        
        if not is_valid:
            self.status_var.set(msg)
            return None

        return (
            parsed["symbol"], parsed["start"], parsed["end"], 
            parsed["out_pct"], parsed["in_pct"], parsed["dur"], 
            ki_freq, ko_freq, parsed["lockup"]
        )

    def _on_run(self):
        """重写运行逻辑：绝对优先本地库，网络挂了也能画"""
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
                self.result_queue.put(("progress", "正在查询本地库"))
                first, last = self.db.get_first_date(symbol), self.db.get_last_date(symbol)
                
                # 只有当本地库确实没有数据，或者要的数据晚于库里的最后一天时，才尝试爬取
                need_crawl = (first is None) or (first > start) or (last and last < end)
                
                crawl_failed = False
                if need_crawl:
                    self.result_queue.put(("progress", "正在尝试补充最新数据"))
                    try:
                        self.crawler.update_symbol(symbol, verbose=False)
                        self.result_queue.put(("db_range", (self.db.get_first_date(symbol), self.db.get_last_date(symbol))))
                    except Exception as e:
                        crawl_failed = True
                        print(f"爬取失败: {e}")
                
                # 无论爬取成没成功，先去库里拿数据
                df = self.db.load(symbol, start=start, end=end)
                
                # 如果设置了 end=今天，但库里只有昨天的数据，load会返回空！
                # 所以如果因为结束日期太新导致 df 为空，我们强制忽略 end，只截取 start 之后的所有可用数据
                if df.empty:
                    df = self.db.load(symbol, start=start)
                    if df.empty:
                        self.result_queue.put(("error", f"{symbol} 范围内完全无数据")); return
                    
                    # 如果强拉出来的数据最后一天仍然小于 start，说明这合约在 start 之后根本没数据
                    if df["date"].iloc[-1] < start:
                        self.result_queue.put(("error", f"{symbol} 在 {start} 之后无数据")); return
                        
                    # 自动修正界面的结束时间，防止用户下次再查报错
                    actual_end_str = df["date"].iloc[-1]
                    self.root.after(0, lambda: self._set_date_range(start, actual_end_str))
                    if crawl_failed:
                        self.root.after(0, lambda: self.status_var.set(f"⚠️ 网络异常，已使用历史数据至 {actual_end_str}"))

                actual_start, actual_end = df["date"].iloc[0], df["date"].iloc[-1]
                
                # 如果没走到上面那个 if，说明 df 原本就有数据。
                # 但如果发生爬取失败，且用户想要的数据大于库里最新数据，也要修正界面结束时间
                if crawl_failed and actual_end < end:
                    self.root.after(0, lambda: self._set_date_range(start, actual_end))
                    self.root.after(0, lambda: self.status_var.set(f"⚠️ 网络异常，已使用历史数据至 {actual_end}"))

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

        # 【新增】：获取频率的中文名，拼到文件名里
        def get_freq_name(freq):
            if freq[0] == "daily": return "每日"
            if freq[0] == "weekly": return "每周"
            if freq[0] == "monthly": return "每月"
            return "每日"

        ki_name = get_freq_name(ki_freq)
        ko_name = get_freq_name(ko_freq)
        
        # 拼装默认文件名：比如 sh000852_每月敲出_每日敲入_detail.csv
        default_name = f"{symbol}_{ko_name}敲出_{ki_name}敲入_detail.csv"

        path = filedialog.asksaveasfilename(
            defaultextension=".csv", 
            initialfile=default_name, 
            filetypes=[("CSV 文件", "*.csv")]
        )
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
                    
                    if exs:
                        shfe_name = "上海期货交易所"
                        target_ex = 0
                        for i, ex in enumerate(exs):
                            if ex == shfe_name:
                                target_ex = i
                                break
                        
                        self.exchange_cb.current(target_ex)
                        
                        ex_code = self.contract_mgr.exchange_code(shfe_name)
                        varieties = self.contract_mgr.get_varieties(ex_code)
                        self.variety_cb["values"] = varieties
                        
                        golden_name = "黄金主连"
                        target_var = 0
                        if golden_name in varieties:
                            target_var = varieties.index(golden_name)
                        
                        self.variety_cb.current(target_var)
                        
                        contracts = self.contract_mgr.get_contracts(ex_code, self.variety_var.get())
                        display = [c.upper() for c in contracts]
                        self.contract_cb["values"] = display
                        if display:
                            self.contract_cb.current(0)
                        
                        self._on_contract_change()
                                
                    self.status_var.set("合约列表就绪"); self.progress_var.set("就绪")
                    
                elif msg_type == "progress": 
                    self.progress_var.set(payload)
                    
                elif msg_type == "db_range":
                    first, last = payload
                    if first and last: 
                        self.db_range_var.set(f"已有: {first} ~ {last}")
                        cur_start, cur_end = self._get_dates()
                        if cur_start < first: cur_start = first
                        if cur_end > last: cur_end = last
                        self._set_date_range(cur_start, cur_end)
                        
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
        self.current_results = payload["results"]   
        self.current_params = payload["params"] 
        
        symbol, df, results, params = payload["symbol"], payload["df"], payload["results"], payload["params"]
        c = Counter(r["color"] for r in results)
        
        self.chart_mgr.draw_chart1(df, results, self.contract_var.get())
        self.chart_mgr.draw_chart2(results)
        self.chart_mgr.draw_chart3(c)
        
        total = len(results)
        green_v = c.get("green", 0)
        blue_v = c.get("blue", 0)
        valid_total = total - c.get("gray", 0)

        if valid_total > 0:
            ko_rate = green_v / valid_total * 100
            no_ki_rate = (green_v + blue_v) / valid_total * 100
            self.stats_ko_var.set(f"敲出率(绿色): \n   {green_v} / {valid_total} = {ko_rate:.1f}%")
            self.stats_ki_var.set(f"未敲入率(绿和蓝): \n   {green_v + blue_v} / {valid_total} = {no_ki_rate:.1f}%")
        else:
            self.stats_ko_var.set("敲出率(绿色): —")
            self.stats_ki_var.set("未敲入率(绿和蓝): —")

        ki_str = f"{params['ki_freq'][0]}" if params['ki_freq'][0] == 'daily' else f"{params['ki_freq'][0]}-{params['ki_freq'][1]}"
        ko_str = f"{params['ko_freq'][0]}" if params['ko_freq'][0] == 'daily' else f"{params['ko_freq'][0]}-{params['ko_freq'][1]}"
        self.status_var.set(f"完成: {symbol} | 观察: 敲入({ki_str}) 敲出({ko_str}) | 数据量: {total}")

    def _open_returns_window(self):
        if not hasattr(self, "current_results") or not self.current_results:
            messagebox.showwarning("提示", "请先点击【运行】进行回测！")
            return
        ReturnsWindow(self.root, self.current_results, self.current_params)

if __name__ == "__main__":
    root = tk.Tk()
    app = FuturesApp(root)
    root.mainloop()
