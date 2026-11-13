# -*- coding: utf-8 -*-
# returns_window.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from returns_calculator import calculate_returns
import csv

class ReturnsWindow(tk.Toplevel):
    def __init__(self, master, results, params):
        super().__init__(master)
        self.results = results
        self.params = params
        self.title("雪球收益率测算面板")
        self.geometry("700x850")
        self.resizable(True, True)
        
        self.export_data = []
        self._build_ui()

    def _build_ui(self):
        # ================= 顶部：参数设定 =================
        param_frame = ttk.LabelFrame(self, text="收益计算参数设定", padding=15)
        param_frame.pack(side=tk.TOP, fill=tk.X, padx=15, pady=(15, 5))

        row1 = tk.Frame(param_frame)
        row1.pack(fill=tk.X, pady=5)
        tk.Label(row1, text="阶段1票息(%):").pack(side=tk.LEFT)
        self.c_early_var = tk.StringVar(value="8.68")
        ttk.Entry(row1, textvariable=self.c_early_var, width=6).pack(side=tk.LEFT, padx=(2, 15))
        
        tk.Label(row1, text="阶段1设定:").pack(side=tk.LEFT)
        self.early_unit_var = tk.StringVar(value="按观察日")
        self.early_unit_cb = ttk.Combobox(row1, textvariable=self.early_unit_var, values=["按观察日", "按周", "按月"], state="readonly", width=8)
        self.early_unit_cb.pack(side=tk.LEFT, padx=2)
        self.early_unit_cb.bind("<<ComboboxSelected>>", self._on_unit_change)
        
        self.early_val_var = tk.StringVar(value="12")
        ttk.Entry(row1, textvariable=self.early_val_var, width=6).pack(side=tk.LEFT, padx=2)

        row2 = tk.Frame(param_frame)
        row2.pack(fill=tk.X, pady=5)
        tk.Label(row2, text="阶段2票息(%):").pack(side=tk.LEFT)
        self.c_late_var = tk.StringVar(value="5.0")
        ttk.Entry(row2, textvariable=self.c_late_var, width=6).pack(side=tk.LEFT, padx=(2, 15))

        row3 = tk.Frame(param_frame)
        row3.pack(fill=tk.X, pady=5)
        tk.Label(row3, text="红利票息(%):").pack(side=tk.LEFT)
        self.c_red_var = tk.StringVar(value="5.0")
        ttk.Entry(row3, textvariable=self.c_red_var, width=6).pack(side=tk.LEFT, padx=(2, 0))

        row4 = tk.Frame(param_frame)
        row4.pack(fill=tk.X, pady=5)
        tk.Label(row4, text="名义本金(元):").pack(side=tk.LEFT)
        self.principal_var = tk.StringVar(value="1000000")
        self.principal_var.trace_add("write", self._update_actual_principal) 
        ttk.Entry(row4, textvariable=self.principal_var, width=12).pack(side=tk.LEFT, padx=(2, 15))
        
        tk.Label(row4, text="保证金(%):").pack(side=tk.LEFT)
        self.margin_var = tk.StringVar(value="15")
        self.margin_var.trace_add("write", self._update_actual_principal)
        ttk.Entry(row4, textvariable=self.margin_var, width=6).pack(side=tk.LEFT, padx=(2, 0))

        tk.Label(row4, text="实际本金:").pack(side=tk.LEFT, padx=(20, 2))
        self.actual_principal_var = tk.StringVar(value="150,000 元")
        tk.Label(row4, textvariable=self.actual_principal_var, fg="#c65911", font=("Arial", 10, "italic")).pack(side=tk.LEFT)

        row5 = tk.Frame(param_frame)
        row5.pack(fill=tk.X, pady=(10, 0))
        strat_text = f"策略设定：敲出 {self.params['out_pct']}% | 敲入 {self.params['in_pct']}% | 时长 {self.params['duration']}周"
        tk.Label(row5, text=strat_text, fg="#555", font=("Arial", 9, "italic")).pack(side=tk.LEFT)

        tk.Button(param_frame, text="开始测算", bg="#1f3864", fg="white", font=("Arial", 11, "bold"), command=self._on_calculate).pack(fill=tk.X, ipady=4, pady=(15, 0))

        # ================= 底部：统计汇总 =================
        bottom_frame = tk.Frame(self)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=(5, 15))
        
        self.summary_var = tk.StringVar(value="📊 有效样本：— 笔 | 胜率：—")
        tk.Label(bottom_frame, textvariable=self.summary_var, font=("Arial", 12, "bold"), fg="#2e7d32").pack(side=tk.LEFT)

        # ================= 中间部分：PanedWindow 可拖拽布局 =================
        # 创建一个垂直的可拖拽面板
        paned = tk.PanedWindow(self, orient=tk.VERTICAL, sashrelief=tk.RAISED, sashwidth=8, bg="#e0e0e0")
        paned.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # ----- 上半部：敲出明细表 -----
        top_table_frame = tk.Frame(paned)
        
        tool_bar = tk.Frame(top_table_frame)
        tool_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        tk.Label(tool_bar, text="敲出收益测算明细", font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        export_btn = tk.Button(tool_bar, text="导出 CSV", bg="#f0f0f0", relief=tk.GROOVE, command=self._export_csv)
        export_btn.pack(side=tk.RIGHT)

        style = ttk.Style()
        style.configure("Treeview", rowheight=32, font=("Arial", 11))
        style.configure("Treeview.Heading", font=("Arial", 11, "bold"))

        columns = ("bucket", "formula", "count", "prob")
        self.tree = ttk.Treeview(top_table_frame, columns=columns, show="headings")
        
        self.tree.heading("bucket", text="敲出周数")
        self.tree.heading("formula", text="票息收益")
        self.tree.heading("count", text="敲出次数")
        self.tree.heading("prob", text="概率")
        
        self.tree.column("bucket", width=60 ,anchor="center")
        self.tree.column("formula", width=150, anchor="center") # 居中
        self.tree.column("count", width=100, anchor="center")
        self.tree.column("prob", width=100, anchor="center")

        scrollbar = ttk.Scrollbar(top_table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ----- 下半部：红利明细表 -----
        bottom_table_frame = tk.Frame(paned)

        blue_frame = ttk.LabelFrame(bottom_table_frame, text="未敲入未敲出（持有到期）红利收益", padding=10)
        blue_frame.pack(fill=tk.BOTH, expand=True)

        blue_cols = ("type", "formula", "count", "prob")
        self.tree_blue = ttk.Treeview(blue_frame, columns=blue_cols, show="headings", height=2)
        self.tree_blue.heading("type", text="类型")
        self.tree_blue.heading("formula", text="红利收益")
        self.tree_blue.heading("count", text="样本数量")
        self.tree_blue.heading("prob", text="概率")
        
        self.tree_blue.column("type", width=60, anchor="center")
        self.tree_blue.column("formula", width=150, anchor="center") # 居中
        self.tree_blue.column("count", width=100, anchor="center")
        self.tree_blue.column("prob", width=100, anchor="center")
        self.tree_blue.pack(fill=tk.BOTH, expand=True)

        # 把两个 Frame 加入 PanedWindow
        paned.add(top_table_frame, minsize=200, stretch="always")
        paned.add(bottom_table_frame, minsize=100, stretch="never")

        self.after(100, self._on_calculate)

    def _update_actual_principal(self, *args):
        """根据名义本金和保证金自动计算实际本金，并格式化显示"""
        try:
            principal = float(self.principal_var.get())
            margin = float(self.margin_var.get())
            actual = principal * margin / 100.0
            self.actual_principal_var.set(f"{int(actual):,} 元")
        except ValueError:
            self.actual_principal_var.set("—")

    def _on_unit_change(self, event=None):
        unit = self.early_unit_var.get()
        if unit == "按周":
            self.tree.heading("bucket", text="敲出周数")
        elif unit == "按月":
            self.tree.heading("bucket", text="敲出月份")
        else:
            self.tree.heading("bucket", text="敲出天数")

    def _on_calculate(self):
        try:
            ui_params = {
                "c_early": float(self.c_early_var.get()),
                "c_late": float(self.c_late_var.get()),
                "c_red": float(self.c_red_var.get()),
                "margin": float(self.margin_var.get()),
                "principal": float(self.principal_var.get()),
                "early_unit": self.early_unit_var.get(),
                "early_val": float(self.early_val_var.get())
            }
            if ui_params["margin"] <= 0 or ui_params["principal"] <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字参数！")
            return

        res = calculate_returns(self.results, self.params, ui_params)

        self.summary_var.set(
            f"📊 有效样本：{res['valid_total']} 笔 | 胜率：{res['win_rate']*100:.1f}%"
        )
        
        self._on_unit_change()

        for row in self.tree.get_children():
            self.tree.delete(row)
        for row in self.tree_blue.get_children():
            self.tree_blue.delete(row)

        self.export_data.clear()
        bucket_data = res["bucket_stats"]
        sorted_keys = sorted(bucket_data.keys(), key=lambda x: bucket_data[x]["sort_key"])
        total_win = res["green"]["count"] + res["blue"]["count"]

        for key in sorted_keys:
            data = bucket_data[key]
            count = data["count"]
            prob = (count / total_win * 100) if total_win > 0 else 0

            self.tree.insert("", tk.END, values=(
                key, data["formula"], count, f"{prob:.1f}%"
            ))
            
            self.export_data.append({
                "敲出时间": key, "票息收益": data["formula"], "敲出次数": count, "概率": f"{prob:.1f}%"
            })

        blue_count = res["blue"]["count"]
        blue_prob = res["blue"]["prob"] * 100
        self.tree_blue.insert("", tk.END, values=(
            "未敲入未敲出", res["blue"]["formula"],  blue_count, f"{blue_prob:.1f}%"
        ))

    def _export_csv(self):
        if not self.export_data:
            messagebox.showwarning("提示", "当前没有数据可导出，请先进行测算。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="雪球收益率测算明细.csv", filetypes=[("CSV 文件", "*.csv")])
        if not path: return
        try:
            with open(path, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=["敲出时间", "票息收益", "敲出次数", "概率"])
                writer.writeheader()
                writer.writerows(self.export_data)
            messagebox.showinfo("成功", f"数据已成功导出至:\n{path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
