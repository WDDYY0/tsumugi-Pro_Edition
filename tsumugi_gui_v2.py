# -*- coding: utf-8 -*-
"""tsumugi 图形化操作界面 v2.2.1（含 MIDI 预览 + 深度卸载 + 手动拍号）"""
import threading, tkinter as tk, re, time, webbrowser, subprocess, json, os, sys
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import traceback, shutil
import urllib.request
import base64

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
INPUT_DIR = PROJECT_ROOT / "InPut"
OUTPUT_DIR = PROJECT_ROOT / "OutPut"
STEM_OUTPUT_ROOT = PROJECT_ROOT / "stem_outputs"

import advanced_separation
import qr_integrity
from midi_previewer import MidiPreviewer

SOFTWARE_VERSION = "v2.2.1"
INTEGRATOR_NAME = "无端的乐音"
CONTACT_EMAIL = "wuduandeyueyin@qq.com"
ORIGINAL_PROJECT_URL = "https://github.com/anime-song/tsumugi"
ORIGINAL_AUTHOR = "anime-song"
ORIGINAL_LICENSE = "MIT License"

# ★★★ Gitee API 更新检查地址 ★★★
UPDATE_CHECK_URL = "https://gitee.com/api/v5/repos/wddyy-melodies/tsumugiupdatekeshihua/contents/version.json"

AUTO_UPDATE_CHECK_DELAY_MS = 2000

# ★★★ 支持的拍号列表 ★★★
TIME_SIGNATURE_OPTIONS = [
    "4/4", "2/4", "3/4", "6/4",
    "3/8", "6/8", "7/8", "9/8", "12/8",
]


def get_dir_size(dir_path: Path) -> float:
    total_size = 0
    if dir_path.exists():
        for f in dir_path.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size
    return total_size / (1024 * 1024)


def center_window(win, width, height):
    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")


def parse_version(v: str):
    v = str(v).strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def fetch_update_info():
    try:
        cache_buster = int(time.time())
        url = UPDATE_CHECK_URL
        if "?" in url:
            url = f"{url}&_t={cache_buster}"
        else:
            url = f"{url}?_t={cache_buster}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "tsumugi-updater/1.0",
                "Cache-Control": "no-cache",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)

        if isinstance(data, dict) and "content" in data and "encoding" in data:
            content_b64 = data.get("content", "")
            content_b64 = content_b64.replace("\n", "").replace("\r", "")
            content_str = base64.b64decode(content_b64).decode("utf-8")
            return json.loads(content_str)

        return data
    except Exception:
        return None


class TextRedirector:
    def __init__(self, text_widget, gui_instance):
        self.text_widget = text_widget
        self.gui = gui_instance

    def write(self, s):
        self.text_widget.insert(tk.END, s)
        self.text_widget.see(tk.END)
        if self.gui.is_converting:
            self.gui.parse_log_for_progress(s)

    def flush(self):
        pass


class TsumugiGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"tsumugi 音频转 MIDI 助手  {SOFTWARE_VERSION}")
        self.root.geometry("980x820")
        self.files_to_process = []
        self.is_converting = False
        self.stop_requested = False
        self.current_process = None
        self.total_start_time = 0
        self.file_start_time = 0
        self.current_progress_target = 0
        self.current_file_index = 0
        self.total_files = 1
        self.current_mode = "3"

        outer = tk.Frame(root)
        outer.pack(fill=tk.BOTH, expand=True)
        notebook = ttk.Notebook(outer)
        notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        tab_main = tk.Frame(notebook)
        notebook.add(tab_main, text="  🎵 转换  ")
        tab_adv = tk.Frame(notebook)
        notebook.add(tab_adv, text="  ⚙️ 高级设置  ")
        tab_midi = tk.Frame(notebook)
        notebook.add(tab_midi, text="  🎹 MIDI预览  ")
        tab_about = tk.Frame(notebook)
        notebook.add(tab_about, text="  ℹ️ 关于…  ")

        self._build_main_tab(tab_main)
        self._build_advanced_tab(tab_adv)
        self._build_about_tab(tab_about)

        self.midi_previewer = MidiPreviewer(tab_midi)
        self.midi_previewer.pack(fill=tk.BOTH, expand=True)

        right_frame = tk.Frame(outer, width=200, bg="#f0f0f0", relief=tk.GROOVE, borderwidth=2)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        right_frame.pack_propagate(False)
        tk.Label(right_frame, text="🧹 缓存清理工具",
                 font=("微软雅黑", 12, "bold"), bg="#f0f0f0").pack(pady=15)
        self.clean_vars = {"cache": tk.BooleanVar(), "input": tk.BooleanVar(), "output": tk.BooleanVar()}
        tk.Checkbutton(right_frame, text="清理音频分离缓存", variable=self.clean_vars["cache"],
                       bg="#f0f0f0", command=self.check_clean_button_state,
                       font=("微软雅黑", 10)).pack(anchor=tk.W, padx=10, pady=5)
        tk.Checkbutton(right_frame, text="清空 InPut 内容", variable=self.clean_vars["input"],
                       bg="#f0f0f0", command=self.check_clean_button_state,
                       font=("微软雅黑", 10)).pack(anchor=tk.W, padx=10, pady=5)
        tk.Checkbutton(right_frame, text="清空 OutPut 内容", variable=self.clean_vars["output"],
                       bg="#f0f0f0", command=self.check_clean_button_state,
                       font=("微软雅黑", 10)).pack(anchor=tk.W, padx=10, pady=5)
        self.btn_clean = tk.Button(right_frame, text="开始清理", command=self.start_cleaning,
                                   bg="#ffcccc", state=tk.DISABLED, width=15, height=2)
        self.btn_clean.pack(pady=20)

        self.root.after(AUTO_UPDATE_CHECK_DELAY_MS, self.auto_check_update_on_startup)

    def _build_main_tab(self, parent):
        frame_top = tk.Frame(parent)
        frame_top.pack(pady=10, anchor=tk.W)
        tk.Label(frame_top, text="待转换音频：").pack(side=tk.LEFT)
        self.lbl_files = tk.Label(frame_top, text="尚未选择文件", fg="blue")
        self.lbl_files.pack(side=tk.LEFT, padx=10)
        tk.Button(frame_top, text="选择文件", command=self.select_files).pack(side=tk.LEFT)

        self.lbl_filenames = tk.Label(parent, text="", fg="gray", font=("微软雅黑", 9),
                                       wraplength=600, justify=tk.LEFT)
        self.lbl_filenames.pack(anchor=tk.W, padx=10, pady=(0, 5))

        # ===== 三栏布局：模式 | 分隔线 | 手动BPM + 手动拍号 =====
        mode_row = tk.Frame(parent)
        mode_row.pack(pady=10, anchor=tk.W, fill=tk.X, padx=10)

        # ---------- 左栏：模式选择 ----------
        left_mode = tk.Frame(mode_row)
        left_mode.pack(side=tk.LEFT, anchor=tk.N)
        tk.Label(left_mode, text="选择转换模式：",
                 font=("微软雅黑", 10, "bold")).pack(anchor=tk.W)
        self.mode_var = tk.StringVar(value="3")
        tk.Radiobutton(left_mode, text="模式1：常规GPU转换（快速，无鼓组）",
                       variable=self.mode_var, value="1",
                       font=("微软雅黑", 9)).pack(anchor=tk.W, pady=2)
        tk.Radiobutton(left_mode, text="模式2：强制CPU转换（稳定兼容，无鼓组）",
                       variable=self.mode_var, value="2",
                       font=("微软雅黑", 9)).pack(anchor=tk.W, pady=2)
        tk.Radiobutton(left_mode, text="模式3：超高精度分轨识别（分轨多，速度慢，硬件要求高）",
                       variable=self.mode_var, value="3",
                       font=("微软雅黑", 9)).pack(anchor=tk.W, pady=2)

        # ---------- 中间：竖直分隔线 ----------
        sep = tk.Frame(mode_row, width=2, bg="#aaa")
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=20, pady=5)

        # ---------- 右栏：手动 BPM + 手动拍号 ----------
        right_panel = tk.Frame(mode_row)
        right_panel.pack(side=tk.LEFT, anchor=tk.N, fill=tk.X, expand=True)

        # ---- 🎵 手动确定 BPM ----
        tk.Label(right_panel, text="🎵 手动确定 BPM",
                 font=("微软雅黑", 10, "bold"), fg="#1a4d8c").pack(anchor=tk.W)

        tk.Label(right_panel,
                 text="如果你已确定这首曲子的速度，\n可勾选此项并手动输入 BPM。",
                 font=("微软雅黑", 8), fg="#666",
                 justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 5))

        self.force_bpm_var = tk.BooleanVar(value=False)
        self.chk_force_bpm = tk.Checkbutton(
            right_panel,
            text="启用（仅当只选 1 个文件时可用）",
            variable=self.force_bpm_var,
            command=self.on_force_bpm_toggle,
            font=("微软雅黑", 9),
            state=tk.DISABLED,
        )
        self.chk_force_bpm.pack(anchor=tk.W)

        bpm_input_row = tk.Frame(right_panel)
        bpm_input_row.pack(anchor=tk.W, pady=(5, 0))
        tk.Label(bpm_input_row, text="曲速 BPM：",
                 font=("微软雅黑", 9)).pack(side=tk.LEFT)
        self.force_bpm_entry = tk.Entry(bpm_input_row, width=8, font=("微软雅黑", 9))
        self.force_bpm_entry.pack(side=tk.LEFT, padx=5)
        self.force_bpm_entry.insert(0, "120")
        self.force_bpm_entry.config(state=tk.DISABLED)
        tk.Label(bpm_input_row, text="（有效范围 30 - 300）",
                 font=("微软雅黑", 8), fg="#888").pack(side=tk.LEFT)

        # ---- 🎼 手动选择拍号 ----
        tk.Label(right_panel, text="🎼 手动选择拍号",
                 font=("微软雅黑", 10, "bold"), fg="#1a4d8c").pack(anchor=tk.W, pady=(15, 0))

        tk.Label(right_panel,
                 text="如果你已确定这首曲子的拍号，\n可勾选此项并手动选择拍号。",
                 font=("微软雅黑", 8), fg="#666",
                 justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 5))

        self.force_ts_var = tk.BooleanVar(value=False)
        self.chk_force_ts = tk.Checkbutton(
            right_panel,
            text="启用（仅当只选 1 个文件时可用）",
            variable=self.force_ts_var,
            command=self.on_force_ts_toggle,
            font=("微软雅黑", 9),
            state=tk.DISABLED,
        )
        self.chk_force_ts.pack(anchor=tk.W)

        ts_input_row = tk.Frame(right_panel)
        ts_input_row.pack(anchor=tk.W, pady=(5, 0))
        tk.Label(ts_input_row, text="拍号：",
                 font=("微软雅黑", 9)).pack(side=tk.LEFT)
        self.force_ts_combo = ttk.Combobox(
            ts_input_row, values=TIME_SIGNATURE_OPTIONS,
            state="disabled", width=8, font=("微软雅黑", 9)
        )
        self.force_ts_combo.pack(side=tk.LEFT, padx=5)
        self.force_ts_combo.set("4/4")
        tk.Label(ts_input_row, text="（常用拍号）",
                 font=("微软雅黑", 8), fg="#888").pack(side=tk.LEFT)

        # 量化选项
        self.quantize_var = tk.BooleanVar(value=False)
        tk.Checkbutton(parent, text="启用自动量化（实验性）", variable=self.quantize_var,
                       font=("微软雅黑", 10, "bold"), fg="#8B0000").pack(anchor=tk.W, pady=5, padx=10)

        frame_btn = tk.Frame(parent)
        frame_btn.pack(pady=8)
        self.btn_start = tk.Button(frame_btn, text="开始转换", command=self.start_processing,
                                   bg="lightgreen", width=15, height=2)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = tk.Button(frame_btn, text="⛔ 强制停止", command=self.stop_processing,
                                  bg="#ff6666", fg="white", width=15, height=2, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.lbl_progress = tk.Label(parent, text="等待开始...", font=("微软雅黑", 10))
        self.lbl_progress.pack(pady=5)
        self.progress = ttk.Progressbar(parent, orient="horizontal", length=600, mode="determinate")
        self.progress.pack(pady=5)
        self.lbl_timer = tk.Label(parent, text="当前文件: 00:00 / 总耗时: 00:00",
                                  font=("微软雅黑", 10, "bold"), fg="#333")
        self.lbl_timer.pack(pady=5)

        frame_log = tk.Frame(parent)
        frame_log.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        tk.Label(frame_log, text="运行日志：").pack(anchor=tk.W)
        self.log_text = tk.Text(frame_log, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        sys.stdout = TextRedirector(self.log_text, self)
        sys.stderr = TextRedirector(self.log_text, self)

    def on_force_bpm_toggle(self):
        if self.force_bpm_var.get():
            self.force_bpm_entry.config(state=tk.NORMAL)
        else:
            self.force_bpm_entry.config(state=tk.DISABLED)

    def on_force_ts_toggle(self):
        if self.force_ts_var.get():
            self.force_ts_combo.config(state="readonly")
        else:
            self.force_ts_combo.config(state="disabled")

    def _build_advanced_tab(self, parent):
        tk.Label(parent, text="🔬 精细音源分离（实验性）",
                 font=("微软雅黑", 14, "bold"), fg="#1a4d8c").pack(pady=15)
        desc = (
            "启用后，将使用 demucs（Meta 开源）替代项目内置的分离器，\n"
            "把人声/鼓/贝斯/其他分离得更细致，再逐轨扒谱。\n\n"
            "⚠️ 注意事项：\n"
            "• 首次使用需点击下方按钮安装 demucs（约 200MB，需联网）\n"
            "• 分离质量极不稳定，且速度会比内置分离慢 2~3 倍\n"
            "• 实验性 demucs 精细分离每次关闭软件后会重置启用勾选\n"
            "• 若已用 UVR5 等分离出 lead/harmony，可放进 InPut 中用模式1逐轨扒谱\n"
        )
        tk.Label(parent, text=desc, font=("微软雅黑", 10), justify=tk.LEFT,
                 fg="#333").pack(pady=10, padx=20, anchor=tk.W)
        tk.Frame(parent, height=2, bg="#ccc").pack(fill=tk.X, padx=20, pady=10)

        self.ext_sep_var = tk.BooleanVar(value=False)
        tk.Checkbutton(parent, text="✅ 启用 demucs 精细分离（仅对模式3生效）",
                       variable=self.ext_sep_var, font=("微软雅黑", 11, "bold"),
                       fg="#8B0000").pack(anchor=tk.W, padx=20, pady=10)

        frame_model = tk.Frame(parent)
        frame_model.pack(anchor=tk.W, padx=20, pady=5)
        tk.Label(frame_model, text="选择 demucs 模型：", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.demucs_model_var = tk.StringVar(value="htdemucs")
        model_names = [m[0] for m in advanced_separation.DEMUCS_MODELS]
        ttk.Combobox(frame_model, textvariable=self.demucs_model_var,
                     values=model_names, state="readonly", width=20).pack(side=tk.LEFT, padx=10)
        tk.Label(parent, text="\n".join([f"  • {m[0]}：{m[1]}" for m in advanced_separation.DEMUCS_MODELS]),
                 font=("微软雅黑", 9), fg="#555", justify=tk.LEFT).pack(anchor=tk.W, padx=40, pady=5)

        tk.Frame(parent, height=2, bg="#ccc").pack(fill=tk.X, padx=20, pady=15)
        tk.Label(parent, text="demucs 状态：",
                 font=("微软雅黑", 10, "bold")).pack(anchor=tk.W, padx=20)
        self.lbl_demucs_status = tk.Label(parent, text="点击下方按钮检测状态",
                                          fg="gray", font=("微软雅黑", 10))
        self.lbl_demucs_status.pack(anchor=tk.W, padx=40, pady=5)

        frame_btn = tk.Frame(parent)
        frame_btn.pack(anchor=tk.W, padx=20, pady=10)
        tk.Button(frame_btn, text="检测 demucs", command=self.check_demucs, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_btn, text="安装 demucs", command=self.install_demucs, width=15,
                  bg="#cce5ff").pack(side=tk.LEFT, padx=5)

        tk.Label(parent, text="💡 提示：检测通过后，回到「🎵 转换」标签页，选择模式3即可。",
                 font=("微软雅黑", 9), fg="#666").pack(anchor=tk.W, padx=20, pady=15)

    def _build_about_tab(self, parent):
        main_row = tk.Frame(parent)
        main_row.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_col = tk.Frame(main_row)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(left_col, text="ℹ️ 关于本软件",
                 font=("微软雅黑", 16, "bold"), fg="#1a4d8c").pack(pady=(10, 15))

        info_frame = tk.Frame(left_col, bg="#f5f8fc", relief=tk.GROOVE, borderwidth=1)
        info_frame.pack(fill=tk.X, padx=20, pady=(0, 12))

        def add_row(par, label, value, url=None):
            row = tk.Frame(par, bg="#f5f8fc")
            row.pack(fill=tk.X, padx=15, pady=5)
            tk.Label(row, text=label, font=("微软雅黑", 10, "bold"),
                     bg="#f5f8fc", width=14, anchor=tk.W).pack(side=tk.LEFT)
            if url:
                link = tk.Label(row, text=value, font=("微软雅黑", 10, "underline"),
                                fg="#1a73e8", bg="#f5f8fc", cursor="hand2")
                link.pack(side=tk.LEFT, anchor=tk.W)
                link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            else:
                tk.Label(row, text=value, font=("微软雅黑", 10),
                         bg="#f5f8fc", anchor=tk.W).pack(side=tk.LEFT)

        add_row(info_frame, "软件版本：", SOFTWARE_VERSION)
        add_row(info_frame, "二次创作整合：", INTEGRATOR_NAME)
        add_row(info_frame, "原项目名称：", "tsumugi")
        add_row(info_frame, "原项目作者：", ORIGINAL_AUTHOR)
        add_row(info_frame, "原项目链接：", ORIGINAL_PROJECT_URL, ORIGINAL_PROJECT_URL)
        add_row(info_frame, "开源协议：", ORIGINAL_LICENSE)

        update_row = tk.Frame(info_frame, bg="#f5f8fc")
        update_row.pack(fill=tk.X, padx=15, pady=(8, 5))
        tk.Label(update_row, text="软件更新：", font=("微软雅黑", 10, "bold"),
                 bg="#f5f8fc", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.btn_update = tk.Button(update_row, text="🔍 检查更新",
                                     command=self.check_update_manual,
                                     font=("微软雅黑", 9),
                                     bg="#e0f0ff", fg="#1a4d8c",
                                     cursor="hand2", relief=tk.RAISED)
        self.btn_update.pack(side=tk.LEFT)

        tk.Frame(left_col, height=2, bg="#ccc").pack(fill=tk.X, padx=20, pady=8)

        note_text = (
            "本软件基于开源项目 tsumugi 二次开发整合。\n"
            "原作者：anime-song（遵循 MIT 开源协议）。\n"
            "特别鸣谢：DeepSeek AI。\n\n"
            "本人（无端的乐音）在原项目基础上做了部分整合与增强：\n"
            "• 一键桌面化图形界面（tkinter GUI）\n"
            "• 三种转换模式（常规GPU / 强制CPU / 超高精度分轨）\n"
            "• 智能音频格式兼容与显存自适应\n"
            "• 日志解析与实时进度条\n"
            "• 分轨 MIDI 独立导出、可选实验性自动量化\n"
            "• 手动固定 BPM（仅单文件）\n"
            "• 手动指定拍号（仅单文件）\n"
            "• MIDI 轨道预览（可视化+播放）\n"
            "• demucs 精细音源分离（可选项）\n"
            "• 强制停止以及缓存一键清理\n"
            "© 以开源精神分享，为人人扒谱而生。"
        )
        tk.Label(left_col, text=note_text, font=("微软雅黑", 9), justify=tk.LEFT,
                 fg="#333", wraplength=560).pack(padx=20, anchor=tk.W)
        tk.Label(left_col, text="♪ 感谢使用，祝你扒谱顺利 ♪",
                 font=("微软雅黑", 11, "italic"), fg="#888").pack(pady=12)

        right_col = tk.Frame(main_row, width=220, bg="#fffaf0",
                              relief=tk.GROOVE, borderwidth=1)
        right_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0), pady=10)
        right_col.pack_propagate(False)

        tk.Label(right_col, text="💝 支持作者",
                 font=("微软雅黑", 13, "bold"), fg="#c0392b",
                 bg="#fffaf0").pack(pady=(20, 5))

        tk.Label(right_col, text="如果觉得本软件不错，\n可以扫码请作者喝一杯咖啡 ☕",
                 font=("微软雅黑", 9), fg="#666", bg="#fffaf0",
                 justify=tk.CENTER).pack(pady=(0, 15))

        self.btn_support = tk.Button(
            right_col,
            text="❤️ 立即支持",
            command=self.show_qr_popup,
            font=("微软雅黑", 12, "bold"),
            bg="#ffb6c1", fg="#8B0000",
            activebackground="#ff8fab", activeforeground="#8B0000",
            width=14, height=2, relief=tk.RAISED, cursor="hand2",
        )
        self.btn_support.pack(pady=10)

        tk.Label(right_col, text="（点击查看收款码）",
                 font=("微软雅黑", 8), fg="#999", bg="#fffaf0").pack(pady=(0, 15))

        tk.Frame(right_col, height=2, bg="#e0d5b8").pack(fill=tk.X, padx=15, pady=(5, 8))

        tk.Label(right_col, text="📮 联系作者",
                 font=("微软雅黑", 12, "bold"), fg="#1a4d8c",
                 bg="#fffaf0").pack(pady=(3, 5))

        tk.Label(right_col,
                 text="遇到问题？\n有想要的新功能？\n请发邮件告诉我！",
                 font=("微软雅黑", 9), fg="#333", bg="#fffaf0",
                 justify=tk.CENTER).pack(pady=(0, 8))

        email_box = tk.Frame(right_col, bg="#eaf4ff", relief=tk.SOLID, borderwidth=1)
        email_box.pack(padx=15, pady=(0, 5), fill=tk.X)

        email_link = tk.Label(email_box, text=CONTACT_EMAIL,
                              font=("微软雅黑", 9, "bold", "underline"),
                              fg="#1a73e8", bg="#eaf4ff", cursor="hand2")
        email_link.pack(pady=6)
        email_link.bind("<Button-1>",
                        lambda e: webbrowser.open(f"mailto:{CONTACT_EMAIL}?subject=AI扒谱工具反馈"))

        tk.Label(right_col, text="（点击邮箱即可发信）",
                 font=("微软雅黑", 8), fg="#999", bg="#fffaf0").pack(pady=(0, 15))

        tk.Frame(right_col, height=2, bg="#e0d5b8").pack(fill=tk.X, padx=15, pady=(5, 8))

        tk.Label(right_col, text="🗑️ 卸载软件",
                 font=("微软雅黑", 12, "bold"), fg="#8B0000",
                 bg="#fffaf0").pack(pady=(3, 5))

        tk.Label(right_col,
                 text="不再需要使用本软件？\n可以一键卸载。",
                 font=("微软雅黑", 9), fg="#666", bg="#fffaf0",
                 justify=tk.CENTER).pack(pady=(0, 8))

        self.btn_uninstall = tk.Button(
            right_col,
            text="🗑️ 一键卸载",
            command=self.uninstall_app,
            font=("微软雅黑", 11, "bold"),
            bg="#ffcccc", fg="#8B0000",
            activebackground="#ffaaaa", activeforeground="#8B0000",
            width=14, height=2, relief=tk.RAISED, cursor="hand2",
        )
        self.btn_uninstall.pack(pady=8)

        tk.Label(right_col, text="（InPut 和 OutPut 中的文件会保留）",
                 font=("微软雅黑", 8), fg="#999", bg="#fffaf0").pack(pady=(0, 10))

    # ============================================================
    #  检查更新
    # ============================================================
    def auto_check_update_on_startup(self):
        def task():
            data = fetch_update_info()
            if data is None:
                return
            try:
                latest_version = data.get("version", "0.0.0")
                download_url = data.get("download_url", "")
                changelog = data.get("changelog", "无更新说明")

                cur = parse_version(SOFTWARE_VERSION)
                latest = parse_version(latest_version)

                if latest > cur:
                    self.root.after(0, lambda: self._show_update_dialog(
                        latest_version, download_url, changelog
                    ))
            except Exception:
                pass

        threading.Thread(target=task, daemon=True).start()

    def _show_update_dialog(self, latest_version, download_url, changelog):
        msg = (
            f"发现新版本！\n\n"
            f"当前版本：{SOFTWARE_VERSION}\n"
            f"最新版本：v{latest_version}\n\n"
            f"更新说明：\n{changelog}\n\n"
            f"是否前往下载？"
        )
        if messagebox.askyesno("发现新版本 🎉", msg):
            if download_url:
                webbrowser.open(download_url)
            else:
                messagebox.showwarning("提示", "更新说明里没有提供下载链接。")

    def check_update_manual(self):
        self.btn_update.config(state=tk.DISABLED, text="🔍 检查中...")
        self.root.update()

        def task():
            try:
                data = fetch_update_info()
                if data is None:
                    raise RuntimeError("无法连接到更新服务器")

                latest_version = data.get("version", "0.0.0")
                download_url = data.get("download_url", "")
                changelog = data.get("changelog", "无更新说明")

                cur = parse_version(SOFTWARE_VERSION)
                latest = parse_version(latest_version)

                if latest > cur:
                    self.root.after(0, lambda: self._show_update_dialog(
                        latest_version, download_url, changelog
                    ))
                else:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "检查更新", f"✅ 已是最新版本 {SOFTWARE_VERSION}"
                    ))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "检查更新失败",
                    f"无法连接到更新服务器。\n\n"
                    f"可能原因：\n"
                    f"· 网络不通\n"
                    f"· 你的 Gitee 仓库不是公开的\n"
                    f"· 更新地址配置错误\n\n"
                    f"错误信息：{e}"
                ))
            finally:
                self.root.after(0, lambda: self.btn_update.config(
                    state=tk.NORMAL, text="🔍 检查更新"))

        threading.Thread(target=task, daemon=True).start()

    # ============================================================
    #  收款码弹窗
    # ============================================================
    def show_qr_popup(self):
        qr_path = PROJECT_ROOT / "resources" / "收款码.png"
        status, msg = qr_integrity.verify_signature(qr_path)

        popup = tk.Toplevel(self.root)
        popup.title("支持作者 ❤️")
        popup.configure(bg="#fffaf0")
        popup.resizable(False, False)
        popup.transient(self.root)

        W, H = 400, 560
        center_window(popup, W, H)

        tk.Label(popup, text="💝 感谢支持",
                 font=("微软雅黑", 18, "bold"), fg="#c0392b",
                 bg="#fffaf0").pack(pady=(20, 5))

        tk.Label(popup, text="请用微信扫码支持作者",
                 font=("微软雅黑", 11), fg="#666",
                 bg="#fffaf0").pack(pady=(0, 15))

        content = tk.Frame(popup, bg="#fffaf0")
        content.pack(pady=5)

        QR_SIZE = 250

        if status == "ok":
            photo = None
            try:
                from PIL import Image, ImageTk
                img = Image.open(str(qr_path)).convert("RGB")
                img = img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            except Exception as e_pil:
                try:
                    raw = tk.PhotoImage(file=str(qr_path))
                    w = raw.width()
                    if w > QR_SIZE:
                        factor = max(1, round(w / QR_SIZE))
                        raw = raw.subsample(factor, factor)
                    photo = raw
                except Exception as e_tk:
                    tk.Label(content,
                             text=f"图片加载失败\n\n"
                                  f"请先运行：uv pip install pillow\n\n"
                                  f"PIL错误：{e_pil}\n\n"
                                  f"tk错误：{e_tk}",
                             font=("微软雅黑", 9), fg="#c00",
                             bg="#fffaf0", justify=tk.CENTER,
                             wraplength=340).pack(pady=40)
                    photo = None

            if photo is not None:
                lbl_img = tk.Label(content, image=photo, bg="#fffaf0")
                lbl_img.image = photo
                lbl_img.pack()
                tk.Label(popup, text="🔒 完整性校验通过",
                         font=("微软雅黑", 10), fg="#006400",
                         bg="#fffaf0").pack(pady=15)

        elif status == "tampered":
            warn = tk.Frame(content, width=QR_SIZE, height=QR_SIZE,
                            bg="#ffe0e0", relief=tk.SUNKEN, borderwidth=2)
            warn.pack()
            warn.pack_propagate(False)
            tk.Label(warn, text="⚠️ 校验失败\n\n收款码已被篡改\n\n请联系软件作者",
                     font=("微软雅黑", 11, "bold"), fg="#c00",
                     bg="#ffe0e0", justify=tk.CENTER).pack(expand=True)
            tk.Label(popup, text="🔓 完整性校验未通过",
                     font=("微软雅黑", 10, "bold"), fg="#c00",
                     bg="#fffaf0").pack(pady=15)

        elif status == "missing_image":
            placeholder = tk.Frame(content, width=QR_SIZE, height=QR_SIZE,
                                    bg="#f0f0f0", relief=tk.SUNKEN, borderwidth=2)
            placeholder.pack()
            placeholder.pack_propagate(False)
            tk.Label(placeholder,
                     text="收款码图片不存在\n\n请将收款码放到\nresources/收款码.png",
                     font=("微软雅黑", 10), fg="#999",
                     bg="#f0f0f0", justify=tk.CENTER).pack(expand=True)

        elif status == "no_signature":
            warn = tk.Frame(content, width=QR_SIZE, height=QR_SIZE,
                            bg="#fff8dc", relief=tk.SUNKEN, borderwidth=2)
            warn.pack()
            warn.pack_propagate(False)
            tk.Label(warn, text="⚠️ 尚未锁定\n\n请运行 lock_qr.py",
                     font=("微软雅黑", 10), fg="#b8860b",
                     bg="#fff8dc", justify=tk.CENTER).pack(expand=True)

        else:
            tk.Label(content, text=f"[状态: {status}]",
                     font=("微软雅黑", 10), fg="#666",
                     bg="#fffaf0").pack(pady=80)

        btn_frame = tk.Frame(popup, bg="#fffaf0")
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="关闭", command=popup.destroy,
                  font=("微软雅黑", 11), bg="#f0f0f0",
                  activebackground="#e0e0e0",
                  width=12, height=1).pack()

        popup.bind("<Escape>", lambda e: popup.destroy())
        popup.grab_set()
        popup.focus_set()

    # ============================================================
    #  一键卸载（3 层流程）
    # ============================================================
    def uninstall_app(self):
        candidates = [
            PROJECT_ROOT / "unins000.exe",
            PROJECT_ROOT / "unins001.exe",
            PROJECT_ROOT / "uninstall.exe",
        ]
        uninstaller = None
        for c in candidates:
            if c.exists():
                uninstaller = c
                break

        if uninstaller is None:
            messagebox.showerror(
                "找不到卸载程序",
                "未找到卸载程序（unins000.exe）。\n\n"
                "可能原因：\n"
                "· 你不是通过安装程序安装的（比如直接从源码运行）\n"
                "· 卸载程序已被删除\n\n"
                "如需卸载，请手动删除整个项目文件夹：\n"
                f"{PROJECT_ROOT}"
            )
            return

        if not messagebox.askyesno(
            "确认卸载",
            "确定要卸载 AI 扒谱工具吗？\n\n"
            "即将进入卸载选项界面。\n\n"
            "是否继续？"
        ):
            return

        choice = self._show_uninstall_choice_dialog()
        if choice is None:
            return

        mode = choice["mode"]
        options = choice["options"]

        if mode == "standard":
            confirm_msg = (
                "即将执行【标准卸载】：\n\n"
                "✅ 会删除：\n"
                "  · 软件本体\n"
                "  · 桌面快捷方式\n"
                "  · 开始菜单项\n\n"
                "🛡️ 会保留：\n"
                "  · Python 环境\n"
                "  · uv 包管理器\n\n"
                "确定要继续吗？"
            )
        else:
            delete_list = []
            if options.get("uninstall_app"):
                delete_list.append("· 软件本体 + 快捷方式")
            if options.get("uninstall_python"):
                delete_list.append("· uv 下载的 Python 缓存")
            if options.get("uninstall_uv"):
                delete_list.append("· uv 包管理器 + 相关配置")
            confirm_msg = (
                "即将执行【深度卸载】：\n\n"
                "✅ 会删除：\n" + "\n".join(delete_list) + "\n\n"
                "此操作不可恢复。\n\n"
                "确定要继续吗？"
            )

        if not messagebox.askyesno("最终确认", confirm_msg):
            return

        try:
            if mode == "deep":
                self._launch_deep_uninstall(uninstaller, options)
            else:
                subprocess.Popen([str(uninstaller)], cwd=str(PROJECT_ROOT))
            self.root.after(800, self.root.destroy)
        except Exception as e:
            messagebox.showerror("启动卸载程序失败",
                                 f"错误信息：\n{e}\n\n"
                                 f"你可以手动双击这个文件运行卸载：\n{uninstaller}")

    def _show_uninstall_choice_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("卸载 AI 扒谱工具")
        dialog.configure(bg="#f5f5f5")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        W, H = 560, 560
        center_window(dialog, W, H)

        result = {"value": None}

        tk.Label(dialog, text="🗑️ 选择卸载方式",
                 font=("微软雅黑", 16, "bold"), fg="#c0392b",
                 bg="#f5f5f5").pack(pady=(15, 5))

        tk.Label(dialog, text="请仔细阅读两种方式的区别，然后选择一种。",
                 font=("微软雅黑", 9), fg="#666",
                 bg="#f5f5f5").pack(pady=(0, 10))

        mode_var = tk.StringVar(value="standard")

        std_frame = tk.Frame(dialog, bg="#e8f5e9",
                              relief=tk.GROOVE, borderwidth=2)
        std_frame.pack(fill=tk.X, padx=25, pady=6)

        tk.Radiobutton(
            std_frame, text="✅ 标准卸载（推荐）",
            variable=mode_var, value="standard",
            font=("微软雅黑", 12, "bold"), fg="#2e7d32",
            bg="#e8f5e9", activebackground="#e8f5e9",
            cursor="hand2"
        ).pack(anchor=tk.W, padx=12, pady=(8, 3))

        tk.Label(std_frame,
                 text="删除软件本体、桌面图标、开始菜单项\n"
                      "保留 Python、uv 等环境（下次装其他软件可能用得上）",
                 font=("微软雅黑", 9), fg="#444", bg="#e8f5e9",
                 justify=tk.LEFT).pack(anchor=tk.W, padx=40, pady=(0, 10))

        deep_frame = tk.Frame(dialog, bg="#ffebee",
                               relief=tk.GROOVE, borderwidth=2)
        deep_frame.pack(fill=tk.X, padx=25, pady=6)

        tk.Radiobutton(
            deep_frame, text="🧹 深度卸载（自定义）",
            variable=mode_var, value="deep",
            font=("微软雅黑", 12, "bold"), fg="#c62828",
            bg="#ffebee", activebackground="#ffebee",
            cursor="hand2"
        ).pack(anchor=tk.W, padx=12, pady=(8, 3))

        tk.Label(deep_frame,
                 text="可以额外选择删除 Python、uv 等环境组件\n"
                      "适合彻底清理电脑时使用",
                 font=("微软雅黑", 9), fg="#444", bg="#ffebee",
                 justify=tk.LEFT).pack(anchor=tk.W, padx=40, pady=(0, 6))

        checks_panel = tk.Frame(deep_frame, bg="#fff5f5",
                                 relief=tk.SUNKEN, borderwidth=1)
        checks_panel.pack(fill=tk.X, padx=20, pady=(0, 10))

        var_app = tk.BooleanVar(value=True)
        var_python = tk.BooleanVar(value=False)
        var_uv = tk.BooleanVar(value=False)

        cb_app = tk.Checkbutton(
            checks_panel, text="卸载软件本体（必选）",
            variable=var_app,
            font=("微软雅黑", 10),
            bg="#fff5f5", activebackground="#fff5f5",
            state=tk.DISABLED, cursor="hand2"
        )
        cb_app.pack(anchor=tk.W, padx=15, pady=(8, 3))

        cb_python = tk.Checkbutton(
            checks_panel, text="卸载 Python（uv 自动下载的缓存）",
            variable=var_python,
            font=("微软雅黑", 10),
            bg="#fff5f5", activebackground="#fff5f5",
            cursor="hand2"
        )
        cb_python.pack(anchor=tk.W, padx=15, pady=3)

        tk.Label(checks_panel,
                 text="    注：仅删除 uv 下载的 Python 缓存，不影响系统独立安装的 Python",
                 font=("微软雅黑", 8), fg="#888", bg="#fff5f5",
                 justify=tk.LEFT).pack(anchor=tk.W, padx=15, pady=(0, 3))

        cb_uv = tk.Checkbutton(
            checks_panel, text="卸载 uv 包管理器（含配置和环境变量）",
            variable=var_uv,
            font=("微软雅黑", 10),
            bg="#fff5f5", activebackground="#fff5f5",
            cursor="hand2"
        )
        cb_uv.pack(anchor=tk.W, padx=15, pady=3)

        def select_all():
            mode_var.set("deep")
            var_app.set(True)
            var_python.set(True)
            var_uv.set(True)
            _update_checkbox_state()

        def _update_checkbox_state():
            if mode_var.get() == "deep":
                cb_python.config(state=tk.NORMAL)
                cb_uv.config(state=tk.NORMAL)
            else:
                cb_python.config(state=tk.DISABLED)
                cb_uv.config(state=tk.DISABLED)
                var_python.set(False)
                var_uv.set(False)

        tk.Button(checks_panel, text="⚡ 一键全部卸载",
                  command=select_all,
                  font=("微软雅黑", 9, "bold"),
                  bg="#ffcccc", fg="#8B0000",
                  cursor="hand2", width=16
                  ).pack(anchor=tk.W, padx=15, pady=(8, 10))

        for rb in std_frame.winfo_children() + deep_frame.winfo_children():
            if isinstance(rb, tk.Radiobutton):
                rb.config(command=_update_checkbox_state)

        _update_checkbox_state()

        btn_row = tk.Frame(dialog, bg="#f5f5f5")
        btn_row.pack(pady=15)

        def on_ok():
            mode = mode_var.get()
            if mode == "deep":
                options = {
                    "uninstall_app": var_app.get(),
                    "uninstall_python": var_python.get(),
                    "uninstall_uv": var_uv.get(),
                }
            else:
                options = {
                    "uninstall_app": True,
                    "uninstall_python": False,
                    "uninstall_uv": False,
                }
            result["value"] = {"mode": mode, "options": options}
            dialog.destroy()

        def on_cancel():
            result["value"] = None
            dialog.destroy()

        tk.Button(btn_row, text="确定", command=on_ok,
                  font=("微软雅黑", 11, "bold"),
                  bg="#4CAF50", fg="white",
                  cursor="hand2", width=12, height=1).pack(side=tk.LEFT, padx=8)

        tk.Button(btn_row, text="取消", command=on_cancel,
                  font=("微软雅黑", 11),
                  bg="#e0e0e0",
                  cursor="hand2", width=12, height=1).pack(side=tk.LEFT, padx=8)

        dialog.focus_set()
        self.root.wait_window(dialog)
        return result["value"]

    def _launch_deep_uninstall(self, uninstaller, options):
        import tempfile
        temp_dir = Path(tempfile.gettempdir())

        cleanup_lines = [
            "@echo off",
            "chcp 65001 >nul",
            "",
            "echo ============================================",
            "echo  正在进行深度清理...",
            "echo ============================================",
            "",
        ]

        if options.get("uninstall_python"):
            cleanup_lines += [
                'echo [1/N] 正在删除 uv 下载的 Python 缓存...',
                r'rd /s /q "%USERPROFILE%\AppData\Local\uv\python" 2>nul',
                "echo   完成",
                "",
            ]

        if options.get("uninstall_uv"):
            cleanup_lines += [
                'echo [2/N] 正在删除 uv 包管理器...',
                r'rd /s /q "%USERPROFILE%\.local\bin" 2>nul',
                r'rd /s /q "%USERPROFILE%\.cargo\bin" 2>nul',
                r'rd /s /q "%USERPROFILE%\AppData\Local\uv" 2>nul',
                r'rd /s /q "%USERPROFILE%\AppData\Roaming\uv" 2>nul',
                'echo   删除环境变量 HF_ENDPOINT...',
                r'reg delete "HKCU\Environment" /v "HF_ENDPOINT" /f >nul 2>&1',
                "echo   完成",
                "",
            ]

        cleanup_lines += [
            'echo ============================================',
            'echo  深度清理完成！',
            'echo ============================================',
            "",
            "pause",
            "",
            r'del /f /q "%~f0" >nul 2>&1',
        ]

        cleanup_path = temp_dir / "tsumugi_cleanup.bat"
        cleanup_path.write_text("\r\n".join(cleanup_lines), encoding="utf-8")

        launcher_lines = [
            "@echo off",
            "chcp 65001 >nul",
            "",
            "timeout /t 2 /nobreak >nul",
            "",
            f'start /wait "" "{uninstaller}"',
            "",
            "timeout /t 3 /nobreak >nul",
            "",
            f'call "{cleanup_path}"',
            "",
            r'del /f /q "%~f0" >nul 2>&1',
        ]

        launcher_path = temp_dir / "tsumugi_uninstall_launcher.bat"
        launcher_path.write_text("\r\n".join(launcher_lines), encoding="utf-8")

        subprocess.Popen(
            ["cmd", "/c", str(launcher_path)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            shell=False,
        )

    # ============================================================
    #  高级设置辅助
    # ============================================================
    def check_demucs(self):
        self.lbl_demucs_status.config(text="检测中...", fg="gray")
        self.root.update()
        if advanced_separation.is_demucs_available():
            self.lbl_demucs_status.config(text="✅ demucs 已安装，可以使用！", fg="green")
        else:
            self.lbl_demucs_status.config(text="❌ demucs 未安装，请点击「安装 demucs」", fg="red")

    def install_demucs(self):
        if not messagebox.askyesno("确认安装",
                                   "将下载安装 demucs（约 200MB）。\n\n"
                                   "请确保网络畅通，安装过程可能需要几分钟。\n\n"
                                   "是否继续？"):
            return
        self.lbl_demucs_status.config(text="安装中，请查看日志...", fg="blue")

        def task():
            ok, msg = advanced_separation.install_demucs()
            self.root.after(0, lambda: self.lbl_demucs_status.config(
                text=("✅ " if ok else "❌ ") + msg,
                fg=("green" if ok else "red")))
        threading.Thread(target=task, daemon=True).start()

    # ============================================================
    #  进度解析
    # ============================================================
    def parse_log_for_progress(self, log_text):
        clean_text = log_text.replace("\r", "\n")
        for line in clean_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "正在处理:" in line or "正在处理：" in line:
                continue

            if self.current_mode in ("1", "2"):
                m = re.search(r'infer:\s*(\d+)%', line)
                if m:
                    infer_pct = int(m.group(1))
                    self.set_file_internal_progress(15 + infer_pct * 0.55, f"AI 扒谱中 {infer_pct}%")
                    continue
                if "预处理音频格式" in line:
                    self.set_file_internal_progress(5, "预处理音频格式...")
                elif "AI 正在扒谱" in line:
                    self.set_file_internal_progress(10, "启动 AI 模型...")
                elif "正在固定 BPM" in line:
                    self.set_file_internal_progress(73, "正在固定 BPM...")
                elif "正在设置拍号" in line:
                    self.set_file_internal_progress(78, "正在设置拍号...")
                elif "正在自动量化" in line:
                    self.set_file_internal_progress(85, "正在自动量化...")
                elif "正在导出分轨" in line:
                    self.set_file_internal_progress(92, "正在导出分轨 MIDI...")
                elif "处理完成" in line:
                    self.set_file_internal_progress(100, "处理完成！")

            elif self.current_mode == "3":
                if "Loading Separation model" in line:
                    self.set_file_internal_progress(10, "加载声部分离模型...")
                elif "Separating stems for" in line or "正在调用 demucs" in line:
                    self.set_file_internal_progress(15, "正在分离声部（这步最耗时）...")
                elif "demucs 分离完成" in line:
                    self.set_file_internal_progress(45, "外部分离完成，开始逐轨转写...")
                elif "正在转写 stem" in line or "Transcribing stem:" in line:
                    self.set_file_internal_progress(55, "正在转写声部...")
                elif "Refining stem instrument labels" in line:
                    self.set_file_internal_progress(68, "正在细化乐器标签...")
                elif "Predicting note velocities" in line:
                    self.set_file_internal_progress(72, "正在预测力度...")
                elif "Updated merged MIDI with predicted velocities" in line:
                    self.set_file_internal_progress(75, "力度预测完成")
                elif "Predicting beat, chord, key" in line:
                    self.set_file_internal_progress(78, "正在预测节拍和弦...")
                elif "Updated merged MIDI with predicted beat/chord/key" in line:
                    self.set_file_internal_progress(80, "节拍和弦完成")
                elif "正在固定 BPM" in line:
                    self.set_file_internal_progress(82, "正在固定 BPM...")
                elif "正在设置拍号" in line:
                    self.set_file_internal_progress(84, "正在设置拍号...")
                elif "正在自动量化" in line:
                    self.set_file_internal_progress(88, "正在自动量化...")
                elif "正在合并所有分轨 MIDI" in line or "Final Merged MIDI" in line:
                    self.set_file_internal_progress(92, "正在合并最终 MIDI...")
                elif "[分轨导出]" in line:
                    self.set_file_internal_progress(96, "正在拆分多轨 MIDI...")
                elif "[完成] 输出 MIDI" in line:
                    self.set_file_internal_progress(100, "处理完成！")

    def set_file_internal_progress(self, file_pct, text):
        overall_pct = (self.current_file_index / self.total_files) * 100 + (file_pct / self.total_files)
        self.update_progress_ui(overall_pct, text, self.current_file_index + 1, self.total_files)

    # ============================================================
    #  缓存清理
    # ============================================================
    def check_clean_button_state(self):
        if any(var.get() for var in self.clean_vars.values()):
            self.btn_clean.config(state=tk.NORMAL)
        else:
            self.btn_clean.config(state=tk.DISABLED)

    def start_cleaning(self):
        tasks = [k for k, v in self.clean_vars.items() if v.get()]
        task_names = {"cache": "音频分离缓存", "input": "InPut 文件夹", "output": "OutPut 文件夹"}
        task_str = "、".join([task_names[t] for t in tasks])
        if not messagebox.askyesno("确认清理",
                                   f"你确定要清理以下内容吗？\n\n{task_str}\n\n此操作不可逆！"):
            return
        total_freed = 0.0
        if self.clean_vars["cache"].get():
            for d in [STEM_OUTPUT_ROOT, PROJECT_ROOT / "separated_stems",
                      PROJECT_ROOT / "stem_midis", PROJECT_ROOT / "external_stems"]:
                if d.exists():
                    total_freed += get_dir_size(d)
                    shutil.rmtree(d)
        if self.clean_vars["input"].get():
            if INPUT_DIR.exists():
                total_freed += get_dir_size(INPUT_DIR)
                [os.remove(f) if f.is_file() else shutil.rmtree(f) for f in INPUT_DIR.iterdir()]
        if self.clean_vars["output"].get():
            if OUTPUT_DIR.exists():
                total_freed += get_dir_size(OUTPUT_DIR)
                [os.remove(f) if f.is_file() else shutil.rmtree(f) for f in OUTPUT_DIR.iterdir()]
        for var in self.clean_vars.values():
            var.set(False)
        self.check_clean_button_state()
        messagebox.showinfo("清理结果", f"✅ 清理完成！\n\n本次共释放了 {total_freed:.2f} MB 空间。")

    # ============================================================
    #  文件选择
    # ============================================================
    def select_files(self):
        files = filedialog.askopenfilenames(
            title="选择音频文件",
            filetypes=[("音频文件", "*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma *.opus *.aiff"),
                       ("所有文件", "*.*")])
        if files:
            self.files_to_process = list(files)
            self.lbl_files.config(text=f"已选择 {len(files)} 个文件")
            names = [Path(f).name for f in files]
            display_text = "、".join(names)
            if len(display_text) > 60:
                display_text = display_text[:60] + "..."
            self.lbl_filenames.config(text=f"📁 {display_text}")

            if len(files) == 1:
                self.chk_force_bpm.config(state=tk.NORMAL,
                                          text="启用（仅当只选 1 个文件时可用）")
                self.chk_force_ts.config(state=tk.NORMAL,
                                         text="启用（仅当只选 1 个文件时可用）")
            else:
                self.force_bpm_var.set(False)
                self.force_bpm_entry.config(state=tk.DISABLED)
                self.chk_force_bpm.config(state=tk.DISABLED,
                                          text="⚠️ 已选多个文件，此项不可用")
                self.force_ts_var.set(False)
                self.force_ts_combo.config(state="disabled")
                self.chk_force_ts.config(state=tk.DISABLED,
                                         text="⚠️ 已选多个文件，此项不可用")

    # ============================================================
    #  开始 / 停止
    # ============================================================
    def start_processing(self):
        if not self.files_to_process:
            messagebox.showwarning("提示", "请先选择音频文件！")
            return
        if self.ext_sep_var.get() and self.mode_var.get() != "3":
            messagebox.showwarning("提示", "「启用 demucs 精细分离」仅对「模式3」生效，已自动帮你切换到模式3。")
            self.mode_var.set("3")
        if self.ext_sep_var.get() and not advanced_separation.is_demucs_available():
            if not messagebox.askyesno("demucs 未安装",
                                       "检测到 demucs 尚未安装。\n\n"
                                       "是否现在去安装？（安装后需要重新开始转换）"):
                return
            messagebox.showinfo("提示", "请切换到「⚙️ 高级设置」标签页，点击「安装 demucs」按钮。")
            return

        # 校验手动 BPM
        force_bpm = None
        if self.force_bpm_var.get():
            if len(self.files_to_process) != 1:
                messagebox.showerror("错误", "手动 BPM 只能在选择 1 个音频文件时启用。")
                return
            bpm_text = self.force_bpm_entry.get().strip()
            try:
                bpm_val = float(bpm_text)
            except ValueError:
                messagebox.showerror("错误", f"BPM 必须是有效数字。\n\n你输入的是：{bpm_text}")
                return
            if bpm_val < 30 or bpm_val > 300:
                messagebox.showerror("错误", f"BPM 必须在 30 到 300 之间。\n\n你输入的是：{bpm_val}")
                return
            force_bpm = bpm_val

        # 校验手动拍号
        force_time_signature = None
        if self.force_ts_var.get():
            if len(self.files_to_process) != 1:
                messagebox.showerror("错误", "手动拍号只能在选择 1 个音频文件时启用。")
                return
            ts_text = self.force_ts_combo.get().strip()
            if not ts_text or "/" not in ts_text:
                messagebox.showerror("错误", f"拍号格式不正确：{ts_text}")
                return
            try:
                num_str, denom_str = ts_text.split("/")
                num = int(num_str)
                denom = int(denom_str)
                force_time_signature = (num, denom)
            except Exception:
                messagebox.showerror("错误", f"无法解析拍号：{ts_text}")
                return

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.stop_requested = False
        self.log_text.delete(1.0, tk.END)
        self.progress["value"] = 0
        self.lbl_progress.config(text="0% - 准备开始...")
        self.is_converting = True
        self.total_start_time = time.time()
        self.current_progress_target = 0
        self.current_file_index = 0
        self.total_files = len(self.files_to_process)
        self.current_mode = self.mode_var.get()
        self._force_bpm = force_bpm
        self._force_time_signature = force_time_signature
        threading.Thread(target=self.run_task, daemon=True).start()
        self.smooth_progress_loop()
        threading.Thread(target=self.update_timer_ui, daemon=True).start()

    def stop_processing(self):
        if not self.is_converting:
            return
        if not messagebox.askyesno("强制停止",
                                   "确定要立刻停止本次转换吗？\n\n"
                                   "正在处理的内容会被中断，已生成的文件会保留。"):
            return
        self.stop_requested = True
        self.lbl_progress.config(text="⛔ 正在停止...")
        print("\n[⛔ 用户请求强制停止] 正在中止当前进程...")
        self._kill_current_process()

    def _kill_current_process(self):
        if self.current_process is None:
            return
        try:
            pid = self.current_process.pid
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            print(f"[⛔] 已终止进程树 (PID={pid})")
        except Exception as e:
            print(f"[⛔] 杀进程失败: {e}")
            try:
                self.current_process.kill()
            except Exception:
                pass

    def smooth_progress_loop(self):
        if not self.is_converting:
            return
        current = self.progress["value"]
        target = self.current_progress_target
        if current < target:
            step = max(0.05, (target - current) * 0.02)
            self.progress["value"] = min(target, current + step)
            if not self.stop_requested:
                self.lbl_progress.config(text=f"处理中... {self.progress['value']:.1f}%")
        self.root.after(100, self.smooth_progress_loop)

    def update_timer_ui(self):
        while self.is_converting:
            cur_time = time.time() - self.file_start_time
            total_time = time.time() - self.total_start_time
            cur_str = time.strftime("%M:%S", time.gmtime(cur_time))
            tot_str = time.strftime("%M:%S", time.gmtime(total_time))
            self.root.after(0, lambda c=cur_str, t=tot_str: self.lbl_timer.config(
                text=f"当前文件: {c} / 总耗时: {t}"))
            time.sleep(1)

    def update_progress_ui(self, overall_percent, text, current_file_num, total_files):
        self.current_progress_target = overall_percent
        if not self.stop_requested:
            self.lbl_progress.config(
                text=f"总进度 {overall_percent:.1f}% (文件 {current_file_num}/{total_files}) - {text}")

    def run_task(self):
        mode = self.mode_var.get()
        do_quantize = self.quantize_var.get()
        use_ext_sep = self.ext_sep_var.get() and mode == "3"
        demucs_model = self.demucs_model_var.get()
        force_bpm = getattr(self, "_force_bpm", None)
        force_ts = getattr(self, "_force_time_signature", None)
        success_files = []
        error_files = []

        for i, audio_file in enumerate(self.files_to_process):
            if self.stop_requested:
                print(f"\n[⛔] 用户已停止，剩余 {len(self.files_to_process) - i} 个文件未处理。")
                break
            self.current_file_index = i
            self.file_start_time = time.time()
            audio_path = Path(audio_file)

            # 拍号在 JSON 里用 [num, denom] 列表传递
            force_ts_json = list(force_ts) if force_ts else None

            params = {
                "mode": mode,
                "file": str(audio_path),
                "device": "cuda" if mode in ("1", "3") else "cpu",
                "do_quantize": do_quantize,
                "use_ext_sep": use_ext_sep,
                "demucs_model": demucs_model,
                "force_bpm": force_bpm,
                "force_time_signature": force_ts_json,
            }
            json_args = json.dumps(params, ensure_ascii=False)
            print(f"\n{'=' * 60}\n  [启动子进程] {audio_path.name}\n{'=' * 60}\n")
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                self.current_process = subprocess.Popen(
                    [sys.executable, "runner.py", json_args],
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW, env=env)
            except Exception as e:
                error_files.append(f"{audio_path.name} (无法启动子进程: {e})")
                self.current_process = None
                continue

            try:
                for line in self.current_process.stdout:
                    self.root.after(0, lambda l=line: self._append_log(l))
                    self.parse_log_for_progress(line)
                    if self.stop_requested:
                        break
            except Exception as e:
                print(f"[主进程] 读取子进程日志异常: {e}")

            try:
                self.current_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._kill_current_process()
                self.current_process.wait()
            returncode = self.current_process.returncode
            self.current_process = None

            if self.stop_requested:
                print(f"\n[⛔] 已停止处理 {audio_path.name}")
                break
            if returncode == 0:
                success_files.append(audio_path.name)
                print(f"\n[✅] {audio_path.name} 处理完成")
            else:
                error_files.append(f"{audio_path.name} (子进程退出码: {returncode})")
                print(f"\n[❌] {audio_path.name} 处理失败")

        self.is_converting = False
        self.current_progress_target = 100.0
        self.progress["value"] = 100 if not self.stop_requested else self.progress["value"]
        self.lbl_progress.config(text=("⛔ 已强制停止" if self.stop_requested else "全部处理完成！"))

        if self.stop_requested:
            summary = (f"⛔ 已强制停止\n\n"
                       f"✅ 已完成: {len(success_files)} 个\n"
                       f"❌ 失败/未完成: "
                       f"{len(error_files) + (len(self.files_to_process) - len(success_files) - len(error_files))} 个")
            self.root.after(0, lambda: messagebox.showwarning("已强制停止", summary))
        else:
            summary = f"🎉 批量处理完成！\n\n✅ 成功: {len(success_files)} 个\n❌ 失败: {len(error_files)} 个\n\n"
            if error_files:
                summary += "失败列表：\n" + "\n".join(error_files)
                self.root.after(0, lambda: messagebox.showerror("部分文件转换失败", summary))
            else:
                summary += "所有文件均完美转换，请查看 OutPut 文件夹。"
                self.root.after(0, lambda: messagebox.showinfo("全部转换成功", summary))
            self.root.after(0, lambda: os.startfile(str(OUTPUT_DIR)))

        self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))

    def _append_log(self, text):
        try:
            self.log_text.insert(tk.END, text)
            self.log_text.see(tk.END)
        except Exception:
            pass


# 程序入口
if __name__ == "__main__":
    _root_dir = Path(__file__).resolve().parent
    (_root_dir / "InPut").mkdir(exist_ok=True)
    (_root_dir / "OutPut").mkdir(exist_ok=True)

    root = tk.Tk()
    app = TsumugiGUI(root)
    root.mainloop()