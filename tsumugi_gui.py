# -*- coding: utf-8 -*-
"""tsumugi 图形化操作界面（文件名显示 + 真实进度 + 计时器 + 实验性量化 + 侧边栏清理）"""
import threading, tkinter as tk, re, time
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import sys, traceback, os, shutil

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
INPUT_DIR = PROJECT_ROOT / "InPut"
OUTPUT_DIR = PROJECT_ROOT / "OutPut"
STEM_OUTPUT_ROOT = PROJECT_ROOT / "stem_outputs"

def get_dir_size(dir_path: Path) -> float:
    total_size = 0
    if dir_path.exists():
        for f in dir_path.rglob("*"):
            if f.is_file(): total_size += f.stat().st_size
    return total_size / (1024 * 1024)

class TextRedirector:
    """将 print 的内容同时输出到 GUI 日志框 和 进度条解析器"""
    def __init__(self, text_widget, gui_instance):
        self.text_widget = text_widget
        self.gui = gui_instance
    def write(self, s):
        self.text_widget.insert(tk.END, s)
        self.text_widget.see(tk.END)
        if self.gui.is_converting:
            self.gui.parse_log_for_progress(s)
    def flush(self): pass

class TsumugiGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("tsumugi 音频转 MIDI 助手")
        self.root.geometry("850x720")
        self.files_to_process = []
        self.is_converting = False
        self.total_start_time = 0
        self.file_start_time = 0
        self.current_progress_target = 0
        self.current_file_index = 0
        self.total_files = 1
        self.current_mode = "3"

        main_container = tk.Frame(root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # ==================== 左侧主功能 ====================
        left_frame = tk.Frame(main_container)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 1. 文件选择
        frame_top = tk.Frame(left_frame)
        frame_top.pack(pady=10, anchor=tk.W)
        tk.Label(frame_top, text="待转换音频：").pack(side=tk.LEFT)
        self.lbl_files = tk.Label(frame_top, text="尚未选择文件", fg="blue")
        self.lbl_files.pack(side=tk.LEFT, padx=10)
        tk.Button(frame_top, text="选择文件", command=self.select_files).pack(side=tk.LEFT)

        # 【新增】文件名显示标签
        self.lbl_filenames = tk.Label(left_frame, text="", fg="gray", font=("微软雅黑", 9), wraplength=550, justify=tk.LEFT)
        self.lbl_filenames.pack(anchor=tk.W, padx=10, pady=(0, 5))

        # 2. 模式选择
        frame_mid = tk.Frame(left_frame)
        frame_mid.pack(pady=10, anchor=tk.W)
        tk.Label(frame_mid, text="选择转换模式：").pack(anchor=tk.W)
        self.mode_var = tk.StringVar(value="3")
        tk.Radiobutton(frame_mid, text="模式1：常规GPU转换（快速）", variable=self.mode_var, value="1").pack(anchor=tk.W)
        tk.Radiobutton(frame_mid, text="模式2：强制CPU转换（稳定兼容）", variable=self.mode_var, value="2").pack(anchor=tk.W)
        tk.Radiobutton(frame_mid, text="模式3：超高精度分轨识别（最强、最慢）", variable=self.mode_var, value="3").pack(anchor=tk.W)

        # 3. 实验性量化开关
        self.quantize_var = tk.BooleanVar(value=False)
        tk.Checkbutton(left_frame, text="启用自动量化（实验性）", variable=self.quantize_var, font=("微软雅黑", 10, "bold"), fg="#8B0000").pack(anchor=tk.W, pady=5)

        # 4. 按钮、进度条、计时器
        frame_btn = tk.Frame(left_frame)
        frame_btn.pack(pady=5)
        self.btn_start = tk.Button(frame_btn, text="开始转换", command=self.start_processing, bg="lightgreen", width=15, height=2)
        self.btn_start.pack()
        
        self.lbl_progress = tk.Label(left_frame, text="等待开始...", font=("微软雅黑", 10))
        self.lbl_progress.pack(pady=5)
        self.progress = ttk.Progressbar(left_frame, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=5)
        self.lbl_timer = tk.Label(left_frame, text="当前文件: 00:00 / 总耗时: 00:00", font=("微软雅黑", 10, "bold"), fg="#333")
        self.lbl_timer.pack(pady=5)

        # 5. 日志区域
        frame_log = tk.Frame(left_frame)
        frame_log.pack(fill=tk.BOTH, expand=True, pady=10)
        tk.Label(frame_log, text="运行日志：").pack(anchor=tk.W)
        self.log_text = tk.Text(frame_log, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        sys.stdout = TextRedirector(self.log_text, self)
        sys.stderr = TextRedirector(self.log_text, self)

        # ==================== 右侧清理侧边栏 ====================
        right_frame = tk.Frame(main_container, width=200, bg="#f0f0f0", relief=tk.GROOVE, borderwidth=2)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        right_frame.pack_propagate(False)
        tk.Label(right_frame, text="🧹 缓存清理工具", font=("微软雅黑", 12, "bold"), bg="#f0f0f0").pack(pady=15)
        self.clean_vars = {"cache": tk.BooleanVar(), "input": tk.BooleanVar(), "output": tk.BooleanVar()}
        tk.Checkbutton(right_frame, text="清理音频分离缓存", variable=self.clean_vars["cache"], bg="#f0f0f0", command=self.check_clean_button_state, font=("微软雅黑", 10)).pack(anchor=tk.W, padx=10, pady=5)
        tk.Checkbutton(right_frame, text="清空 InPut 内容", variable=self.clean_vars["input"], bg="#f0f0f0", command=self.check_clean_button_state, font=("微软雅黑", 10)).pack(anchor=tk.W, padx=10, pady=5)
        tk.Checkbutton(right_frame, text="清空 OutPut 内容", variable=self.clean_vars["output"], bg="#f0f0f0", command=self.check_clean_button_state, font=("微软雅黑", 10)).pack(anchor=tk.W, padx=10, pady=5)
        self.btn_clean = tk.Button(right_frame, text="开始清理", command=self.start_cleaning, bg="#ffcccc", state=tk.DISABLED, width=15, height=2)
        self.btn_clean.pack(pady=20)

    # ==================== 核心：日志解析进度条 ====================
    def parse_log_for_progress(self, log_text):
        clean_text = log_text.replace("\r", "\n")
        for line in clean_text.split("\n"):
            line = line.strip()
            if not line: continue
            if "正在处理:" in line or "正在处理：" in line: continue

            # ==================== 模式1/模式2：抓取 tqdm 进度条 ====================
            if self.current_mode in ("1", "2"):
                m = re.search(r'infer:\s*(\d+)%', line)
                if m:
                    infer_pct = int(m.group(1))
                    file_internal = 15 + infer_pct * 0.70
                    self.set_file_internal_progress(file_internal, f"AI 扒谱中 {infer_pct}%")
                    continue
                if "预处理音频格式" in line: self.set_file_internal_progress(5, "预处理音频格式...")
                elif "AI 正在扒谱" in line: self.set_file_internal_progress(10, "启动 AI 模型...")
                elif "正在自动量化" in line: self.set_file_internal_progress(88, "正在自动量化...")
                elif "正在导出分轨" in line: self.set_file_internal_progress(95, "正在导出分轨 MIDI...")
                elif "处理完成" in line: self.set_file_internal_progress(100, "处理完成！")

            # ==================== 模式3：解析详细日志 ====================
            elif self.current_mode == "3":
                if "Loading Separation model" in line: self.set_file_internal_progress(10, "加载声部分离模型...")
                elif "Separating stems for" in line: self.set_file_internal_progress(15, "正在分离声部（这步最耗时）...")
                elif "Transcribing stem: bass" in line: self.set_file_internal_progress(20, "正在转写贝斯...")
                elif "Transcribing stem: drums" in line: self.set_file_internal_progress(24, "正在转写鼓组...")
                elif "Transcribing stem: guitar" in line: self.set_file_internal_progress(28, "正在转写吉他...")
                elif "Transcribing stem: other" in line: self.set_file_internal_progress(32, "正在转写其他乐器...")
                elif "Transcribing stem: piano" in line: self.set_file_internal_progress(36, "正在转写钢琴...")
                elif "Transcribing stem: vocals" in line: self.set_file_internal_progress(40, "正在转写人声...")
                elif "Refining stem instrument labels" in line: self.set_file_internal_progress(50, "正在细化乐器标签...")
                elif "Refined stem: bass" in line: self.set_file_internal_progress(55, "贝斯细化完成")
                elif "Refined stem: guitar" in line: self.set_file_internal_progress(60, "吉他细化完成")
                elif "Refined stem: other" in line: self.set_file_internal_progress(65, "其他乐器细化完成")
                elif "Refined stem: piano" in line: self.set_file_internal_progress(70, "钢琴细化完成")
                elif "Predicting note velocities" in line: self.set_file_internal_progress(75, "正在预测力度...")
                elif "Updated merged MIDI with predicted velocities" in line: self.set_file_internal_progress(80, "力度预测完成")
                elif "Predicting beat, chord, key" in line: self.set_file_internal_progress(85, "正在预测节拍和弦...")
                elif "Updated merged MIDI with predicted beat/chord/key" in line: self.set_file_internal_progress(90, "节拍和弦完成")
                elif "Final Merged MIDI" in line: self.set_file_internal_progress(95, "正在合并最终 MIDI...")
                elif "[分轨导出]" in line: self.set_file_internal_progress(98, "正在拆分多轨 MIDI...")
                elif "[完成] 输出 MIDI" in line: self.set_file_internal_progress(100, "处理完成！")

    def set_file_internal_progress(self, file_pct, text):
        overall_pct = (self.current_file_index / self.total_files) * 100 + (file_pct / self.total_files)
        self.update_progress_ui(overall_pct, text, self.current_file_index + 1, self.total_files)

    # ==================== 界面辅助函数 ====================
    def check_clean_button_state(self):
        if any(var.get() for var in self.clean_vars.values()): self.btn_clean.config(state=tk.NORMAL)
        else: self.btn_clean.config(state=tk.DISABLED)

    def start_cleaning(self):
        tasks = [k for k, v in self.clean_vars.items() if v.get()]
        task_names = {"cache": "音频分离缓存", "input": "InPut 文件夹", "output": "OutPut 文件夹"}
        task_str = "、".join([task_names[t] for t in tasks])
        if not messagebox.askyesno("确认清理", f"你确定要清理以下内容吗？\n\n{task_str}\n\n此操作不可逆！"): return
        total_freed = 0.0
        if self.clean_vars["cache"].get():
            for d in [STEM_OUTPUT_ROOT, PROJECT_ROOT / "separated_stems", PROJECT_ROOT / "stem_midis"]:
                if d.exists(): total_freed += get_dir_size(d); shutil.rmtree(d)
        if self.clean_vars["input"].get():
            if INPUT_DIR.exists(): total_freed += get_dir_size(INPUT_DIR); [os.remove(f) if f.is_file() else shutil.rmtree(f) for f in INPUT_DIR.iterdir()]
        if self.clean_vars["output"].get():
            if OUTPUT_DIR.exists(): total_freed += get_dir_size(OUTPUT_DIR); [os.remove(f) if f.is_file() else shutil.rmtree(f) for f in OUTPUT_DIR.iterdir()]
        for var in self.clean_vars.values(): var.set(False)
        self.check_clean_button_state()
        messagebox.showinfo("清理结果", f"✅ 清理完成！\n\n本次共释放了 {total_freed:.2f} MB 空间。")

    def select_files(self):
        files = filedialog.askopenfilenames(title="选择音频文件", filetypes=[("音频文件", "*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma *.opus *.aiff"), ("所有文件", "*.*")])
        if files:
            self.files_to_process = list(files)
            self.lbl_files.config(text=f"已选择 {len(files)} 个文件")
            # 【新增】显示文件名
            names = [Path(f).name for f in files]
            display_text = "、".join(names)
            if len(display_text) > 60:
                display_text = display_text[:60] + "..."
            self.lbl_filenames.config(text=f"📁 {display_text}")

    def start_processing(self):
        if not self.files_to_process: messagebox.showwarning("提示", "请先选择音频文件！"); return
        self.btn_start.config(state=tk.DISABLED)
        self.log_text.delete(1.0, tk.END)
        self.progress["value"] = 0
        self.lbl_progress.config(text="0% - 准备开始...")
        self.is_converting = True
        self.total_start_time = time.time()
        self.current_progress_target = 0
        self.current_file_index = 0
        self.total_files = len(self.files_to_process)
        self.current_mode = self.mode_var.get()
        
        threading.Thread(target=self.run_task, daemon=True).start()
        self.smooth_progress_loop()
        threading.Thread(target=self.update_timer_ui, daemon=True).start()

    def smooth_progress_loop(self):
        if not self.is_converting: return
        current = self.progress["value"]
        target = self.current_progress_target
        if current < target:
            step = max(0.05, (target - current) * 0.02)
            self.progress["value"] = min(target, current + step)
            self.lbl_progress.config(text=f"处理中... {self.progress['value']:.1f}%")
        self.root.after(100, self.smooth_progress_loop)

    def update_timer_ui(self):
        while self.is_converting:
            cur_time = time.time() - self.file_start_time
            total_time = time.time() - self.total_start_time
            cur_str = time.strftime("%M:%S", time.gmtime(cur_time))
            tot_str = time.strftime("%M:%S", time.gmtime(total_time))
            self.root.after(0, lambda c=cur_str, t=tot_str: self.lbl_timer.config(text=f"当前文件: {c} / 总耗时: {t}"))
            time.sleep(1)

    def update_progress_ui(self, overall_percent, text, current_file_num, total_files):
        self.current_progress_target = overall_percent
        self.lbl_progress.config(text=f"总进度 {overall_percent:.1f}% (文件 {current_file_num}/{total_files}) - {text}")

    def run_task(self):
        mode = self.mode_var.get()
        success_files = []
        error_files = []
        do_quantize = self.quantize_var.get()
        
        if mode == "3": import run_stem_pipeline as pipeline; func = pipeline.process_one; device_arg = "cuda"
        elif mode == "1": import run_gpu_pipeline as pipeline; func = pipeline.process_one; device_arg = "cuda"
        else: import run_cpu_pipeline as pipeline; func = pipeline.process_one; device_arg = None

        for i, audio_file in enumerate(self.files_to_process):
            self.current_file_index = i
            self.file_start_time = time.time()
            
            def make_callback(idx, base):
                def cb(pct, text):
                    pass  # 现由日志解析控制进度，此回调留作备用
                return cb
            current_callback = make_callback(i, 0)

            try:
                if device_arg: func(Path(audio_file), device_arg, progress_cb=current_callback, do_quantize=do_quantize)
                else: func(Path(audio_file), progress_cb=current_callback, do_quantize=do_quantize)
                success_files.append(Path(audio_file).name)
            except Exception as e:
                err_msg = str(e)[:200]
                error_files.append(f"{Path(audio_file).name} (原因: {err_msg})")
                print(f"\n[❌ 转换失败] {Path(audio_file).name}\n错误详情: {e}\n")
                traceback.print_exc()

        self.current_progress_target = 100.0
        self.progress["value"] = 100
        self.lbl_progress.config(text="全部处理完成！")
        self.is_converting = False

        summary = f"🎉 批量处理完成！\n\n✅ 成功: {len(success_files)} 个\n❌ 失败: {len(error_files)} 个\n\n"
        if error_files: summary += "失败列表：\n" + "\n".join(error_files); self.root.after(0, lambda: messagebox.showerror("部分文件转换失败", summary))
        else: summary += "所有文件均完美转换，请查看 OutPut 文件夹。"; self.root.after(0, lambda: messagebox.showinfo("全部转换成功", summary))
        self.root.after(0, lambda: os.startfile(str(OUTPUT_DIR)))
        self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))

if __name__ == "__main__":
    root = tk.Tk(); app = TsumugiGUI(root); root.mainloop()