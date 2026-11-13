# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import matplotlib.dates as mdates
from matplotlib.collections import LineCollection
from tkinter import filedialog
from collections import Counter

COLOR_MAP = {"green": "#4a7c4e", "yellow": "#ffc000", "red": "#ff0000", "blue": "#4a9acb", "gray": "#a6a6a6"}
LEGEND_LABELS = {
    "green":  "敲出",          
    "yellow": "敲入未敲出(高于期初)",  
    "red":    "敲入未敲出(低于期初)",  
    "blue":   "未敲入未敲出",
    "gray":   "数据不足",
}
LEGEND_ORDER = ["green", "yellow", "red", "blue", "gray"]
PIE_ORDER = ["green", "yellow", "red", "blue"]

class ChartManager:
    def __init__(self, app):
        self.app = app  # 引用主 GUI 实例
        
        # 记录缩放/平移状态
        self._drag_start_x = None
        self._drag_start_xlim = None
        self._full_xlim = None
        self._full_ylim = None
        
        # 辅助线记录
        self.guide_lines = []
        self.guide_texts = []

    def draw_chart1(self, df, results, contract_name):
        ax1 = self.app.ax1
        ax1.clear()

        # 清空之前的辅助线标记
        self.clear_guide_lines()

        dt_list = pd.to_datetime(df["date"]).tolist()
        x = mdates.date2num(dt_list)
        y = df["close"].astype(float).values
        
        seg_colors, seg_list = [], []
        for i in range(1, len(x)):
            if (dt_list[i] - dt_list[i - 1]).days > 7: continue
            seg_list.append([(x[i - 1], y[i - 1]), (x[i], y[i])])
            seg_colors.append(COLOR_MAP.get(results[i - 1]["color"], "#cccccc"))

        if seg_list:
            ax1.add_collection(LineCollection(np.array(seg_list), colors=seg_colors, linewidths=1, zorder=2))

        self._full_xlim = (x.min(), x.max())
        ax1.set_xlim(x.min(), x.max())
        
        y_min, y_max = y.min(), y.max()
        margin = (y_max - y_min) * 0.05 if y_max > y_min else 1
        self._full_ylim = (y_min - margin, y_max + margin)
        ax1.set_ylim(self._full_ylim)

        for key in LEGEND_ORDER: 
            ax1.plot([], [], color=COLOR_MAP[key], linewidth=2, label=LEGEND_LABELS[key])
        
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax1.set_title(f"日线折线图 - {contract_name}", fontsize=11)
        ax1.tick_params(labelsize=9)
        ax1.grid(True, linestyle="--", alpha=0.4)
        ax1.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9, framealpha=0.9)
        
        self.app.fig1.subplots_adjust(left=0.08, right=0.85, top=0.92, bottom=0.18)
        self.app.canvas1.draw_idle()

    def draw_chart2(self, results):
        ax2 = self.app.ax2
        ax2.clear()
        ko_months = [r["ko_month"] for r in results if r["ko_month"] > 0]
        if not ko_months:
            ax2.set_title("无敲出点")
            self.app.canvas2.draw_idle()
            return
            
        counter = Counter(ko_months)
        months = sorted(counter.keys())
        counts = [counter[m] for m in months]
        bars = ax2.bar([str(m) for m in months], counts, color="#839958", alpha=0.85, width=0.35)
        
        for bar, cnt in zip(bars, counts):
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts) * 0.02, 
                     str(cnt), ha="center", va="bottom", fontsize=9)
            
        ax2.set_title("敲出月份分布统计", fontsize=11)
        ax2.tick_params(labelsize=9)
        ax2.grid(True, linestyle="--", alpha=0.4, axis="y")
        ax2.set_xticks(range(len(months)))
        ax2.set_xticklabels([f"{m:g}月" for m in months], rotation=0, fontsize=9)
        
        self.app.fig2.subplots_adjust(left=0.10, right=0.97, top=0.88, bottom=0.22)
        self.app.canvas2.draw_idle()

    def draw_chart3(self, counter):
        ax3 = self.app.ax3
        ax3.clear()
        values = [counter.get(k, 0) for k in PIE_ORDER]
        labels = [LEGEND_LABELS[k] for k in PIE_ORDER]
        colors = [COLOR_MAP[k] for k in PIE_ORDER]
        total = sum(values)
        
        if total == 0:
            ax3.set_title("无有效数据")
            self.app.canvas3.draw_idle()
            return
            
        filtered = [(v, l, c) for v, l, c in zip(values, labels, colors) if v > 0]
        values, labels, colors = [x[0] for x in filtered], [x[1] for x in filtered], [x[2] for x in filtered]

        wedges, _ = ax3.pie(values, colors=colors, startangle=90, counterclock=False, 
                            wedgeprops={"edgecolor": "white", "linewidth": 0.25}, radius=0.62, center=(-0.65, 0))
        
        for w, v in zip(wedges, values):
            ang = (w.theta2 + w.theta1) / 2
            x, y = np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))
            ax3.annotate(f"{v} ({v/total*100:.1f}%)", 
                         xy=(-0.65 + x*0.62, y*0.62), xytext=(-0.65 + x*0.8, y*0.8), 
                         ha="left" if x>=0 else "right", va="center", fontsize=8, 
                         arrowprops=dict(arrowstyle="-", color="#999999", lw=0.8))

        ax3.legend(wedges, labels, loc="upper left", bbox_to_anchor=(0.65, 0.98), fontsize=8, frameon=False)
        ax3.set_aspect("equal")
        ax3.set_xlim(-1.35, 1.35)
        ax3.set_ylim(-1.0, 1.0)
        ax3.axis("off")
        
        self.app.fig3.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.02)
        self.app.canvas3.draw_idle()

    # ================= 辅助线相关 =================

    def clear_guide_lines(self):
        """清除辅助线和文字"""
        for line in self.guide_lines:
            try: line.remove()
            except: pass
        self.guide_lines = []
        
        for text in self.guide_texts:
            try: text.remove()
            except: pass
        self.guide_texts = []
        if hasattr(self.app, 'canvas1'):
            self.app.canvas1.draw_idle()

    def toggle_guide_lines(self):
        """响应勾选框，显示或隐藏辅助线"""
        if not self.app.show_guide_var.get():
            self.clear_guide_lines()
            return

        self.clear_guide_lines()
        
        date_str = self.app.guide_date_var.get().strip()
        if not date_str:
            self.app.status_var.set("⚠️ 请先在输入框填写辅助线日期（如 2023-01-01）")
            self.app.show_guide_var.set(False)
            return
            
        import datetime
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self.app.status_var.set("⚠️ 日期格式错误，请使用 YYYY-MM-DD")
            self.app.show_guide_var.set(False)
            return

        if hasattr(self.app, 'current_results') and self.app.current_results:
            self.draw_fixed_guide_lines(date_str, self.app.current_results)

    def draw_fixed_guide_lines(self, target_date, results):
        """根据指定的日期画敲入/敲出辅助线"""
        self.clear_guide_lines()

        # 找离输入日期最近的一个交易日数据
        target_r = None
        for r in results:
            if r["date"] >= target_date:
                target_r = r
                break
        if not target_r:
            self.app.status_var.set(f"⚠️ 找不到 {target_date} 之后的数据")
            return

        base_price = target_r["price"]
        out_pct = self.app.current_params.get("out_pct", 100) / 100.0
        in_pct = self.app.current_params.get("in_pct", 100) / 100.0
        out_price = base_price * out_pct
        in_price = base_price * in_pct

        # ================= 【核心修复】：自动扩展 Y 轴 =================
        # 获取当前图表的 Y 轴范围
        current_ylim = self.app.ax1.get_ylim()
        new_y_min = min(current_ylim[0], in_price, out_price)
        new_y_max = max(current_ylim[1], in_price, out_price)
        
        # 上下留出 5% 的空间，避免线贴着边框
        padding = (new_y_max - new_y_min) * 0.05
        self.app.ax1.set_ylim(new_y_min - padding, new_y_max + padding)
        # ==============================================================

        # 画横线
        line_out = self.app.ax1.axhline(y=out_price, color="#253d23", linestyle="--", linewidth=0.75, alpha=0.8, zorder=5)
        line_in = self.app.ax1.axhline(y=in_price, color="#AF1E23", linestyle="--", linewidth=0.75, alpha=0.8, zorder=5)
        self.guide_lines = [line_out, line_in]

        # 画文字
        text_out = self.app.ax1.text(0.01, out_price, f" 敲出 ({out_price:.2f})", transform=self.app.ax1.get_yaxis_transform(), color="#253d23", verticalalignment='bottom', fontsize=9, zorder=6)
        text_in = self.app.ax1.text(0.01, in_price, f" 敲入 ({in_price:.2f})", transform=self.app.ax1.get_yaxis_transform(), color="#AF1E23", verticalalignment='top', fontsize=9, zorder=6)
        self.guide_texts = [text_out, text_in]

        self.app.canvas1.draw_idle()
        self.app.status_var.set(f"📍 已添加基准日 {target_r['date']} 的辅助线")

    # ================= 交互控制 =================

    def zoom(self, factor):
        ax1 = self.app.ax1
        self._zoom_at((ax1.get_xlim()[0] + ax1.get_xlim()[1]) / 2, factor)

    def reset_zoom(self):
        ax1 = self.app.ax1
        if self._full_xlim: ax1.set_xlim(self._full_xlim)
        if self._full_ylim: ax1.set_ylim(self._full_ylim)
        # 重置时也把辅助线清了
        self.app.show_guide_var.set(False)
        self.clear_guide_lines()
        self.app.canvas1.draw_idle()

    def on_scroll(self, event):
        if event.inaxes != self.app.ax1: return
        self._zoom_at(event.xdata, 1.2 if event.button == 'up' else 0.8)

    def _zoom_at(self, xcenter, factor):
        ax1 = self.app.ax1
        xlim = ax1.get_xlim()
        width = xlim[1] - xlim[0]
        new_width = width / factor
        relx = (xlim[1] - xcenter) / width
        new_x0 = xcenter - new_width * (1 - relx)
        new_x1 = xcenter + new_width * relx
        
        if self._full_xlim:
            new_x0 = max(new_x0, self._full_xlim[0])
            new_x1 = min(new_x1, self._full_xlim[1])
            
        ax1.set_xlim(new_x0, new_x1)
        self.app.canvas1.draw_idle()

    def on_press(self, event):
        if event.inaxes == self.app.ax1 and event.button == 1:
            self._drag_start_x = event.xdata
            self._drag_start_xlim = self.app.ax1.get_xlim()
            self.app.canvas1.get_tk_widget().config(cursor="fleur")

    def on_release(self, event):
        self._drag_start_x = None
        try: self.app.canvas1.get_tk_widget().config(cursor="")
        except: pass

    def on_motion(self, event):
        # 1. 原有的拖拽平移逻辑
        if self._drag_start_x is not None and event.inaxes == self.app.ax1 and event.xdata is not None:
            dx = self._drag_start_x - event.xdata
            x0, x1 = self._drag_start_xlim
            nx0, nx1 = x0 + dx, x1 + dx
            if self._full_xlim:
                if nx0 < self._full_xlim[0]: nx0, nx1 = self._full_xlim[0], self._full_xlim[0] + (x1-x0)
                if nx1 > self._full_xlim[1]: nx0, nx1 = self._full_xlim[1] - (x1-x0), self._full_xlim[1]
            self.app.ax1.set_xlim(nx0, nx1)
            self.app.canvas1.draw_idle()
            
        # 2. 悬停显示坐标
        if event.inaxes == self.app.ax1 and event.xdata is not None and event.ydata is not None:
            try: 
                date_str = mdates.num2date(event.xdata).strftime('%Y-%m-%d')
                self.app.coord_var.set(f"{date_str} {event.ydata:,.2f}")
            except: pass
        else: 
            self.app.coord_var.set("—")

    def save_chart1(self, contract_name):
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile=f"{contract_name or 'chart'}.png")
        if path:
            try: 
                self.app.fig1.savefig(path, dpi=300, bbox_inches="tight")
                self.app.status_var.set(f"已保存: {path}")
            except Exception as e: 
                self.app.status_var.set(f"保存失败: {e}")
