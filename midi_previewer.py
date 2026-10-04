# -*- coding: utf-8 -*-
"""MIDI 轨道预览器：多轨彩色显示 + 小节网格 + 时间轴 + 播放 + 乐器名（只读）"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import time
import pretty_midi

TRACK_COLORS = [
    "#4A90E2", "#E94B3C", "#50E3C2", "#F5A623", "#BD10E0",
    "#7ED321", "#F8E71C", "#B8E986", "#9B9B9B", "#D0021B",
    "#8B572A", "#417505", "#0A4C8C", "#7B16B0", "#B05C00",
]

GM_INSTRUMENT_NAMES = [
    "原声大钢琴", "明亮钢琴", "电钢琴", "酒吧钢琴", "电钢琴1", "电钢琴2", "羽管键琴", "击弦古钢琴",
    "钢片琴", "钟琴", "音乐盒", "颤音琴", "马林巴", "木琴", "管钟", "扬琴",
    "风琴", "打击风琴", "摇滚风琴", "教堂风琴", "簧风琴", "手风琴", "口琴", "探戈手风琴",
    "尼龙弦吉他", "钢弦吉他", "爵士电吉他", "清音电吉他", "闷音电吉他", "过载吉他", "失真吉他", "吉他泛音",
    "原声贝斯", "指弹电贝斯", "拨片电贝斯", "无品贝斯", "击弦贝斯1", "击弦贝斯2", "合成贝斯1", "合成贝斯2",
    "小提琴", "中提琴", "大提琴", "低音提琴", "弦乐颤音", "弦乐拨奏", "竖琴", "定音鼓",
    "弦乐合奏1", "弦乐合奏2", "合成弦乐1", "合成弦乐2", "人声啊", "管弦乐", "铜管乐", "合成铜管",
    "萨克斯", "中音萨克斯", "次中音萨克斯", "上低音萨克斯", "双簧管", "英国管", "巴松管", "单簧管",
    "短笛", "长笛", "竖笛", "排箫", "吹瓶", "尺八", "哨笛", "陶笛",
    "方波主音", "锯齿波主音", "汽笛风琴主音", "芦笛主音", "夏威夷滑棒主音", "合唱主音", "五度音主音", "贝斯+主音",
    "新时代钢琴垫", "温暖垫", "复音合成垫", "合唱垫", "弓弦垫", "金属垫", "光环垫", "扫掠垫",
    "雨滴", "音轨", "水晶", "大气", "明亮", "地精", "回声", "科幻",
    "西塔琴", "班卓琴", "三味线", "日本筝", "卡林巴", "风笛", "民间小提琴", "唢呐",
    "叮当铃", "阿哥哥", "钢鼓", "木质鼓", "太鼓", "旋律鼓", "合成鼓", "反向钹",
    "吉他品噪", "呼吸声", "海浪", "鸟鸣", "电话铃", "直升机", "掌声", "枪声",
]


def get_instrument_name(program, is_drum):
    if is_drum:
        return "鼓组"
    try:
        p = int(program)
        if 0 <= p < len(GM_INSTRUMENT_NAMES):
            return GM_INSTRUMENT_NAMES[p]
    except Exception:
        pass
    return f"乐器{p}"


DEFAULT_PIXELS_PER_SECOND = 80


class MidiPreviewer(ttk.Frame):
    """MIDI 预览器 Tab"""

    def __init__(self, parent):
        super().__init__(parent)
        self.midi_data = None
        self.midi_path = None
        self.tracks = []
        self.total_duration = 0.0
        self.pixels_per_second = DEFAULT_PIXELS_PER_SECOND
        self.scroll_offset = 0.0
        self.pitch_min = 21
        self.pitch_max = 108
        self.is_playing = False
        self.play_start_time = 0.0
        self.play_start_offset = 0.0
        self.playback_position = 0.0
        self.midi_output = None
        self.midi_available = False
        self.midi_device_name = ""

        self.downbeats = []
        self.bpm = 120.0
        self.time_signature = (4, 4)

        self._init_pygame_midi()
        self._build_ui()

    # ============================================================
    #  ★★★ 关键修复：优先选择 GS Wavetable Synth ★★★
    # ============================================================
    def _init_pygame_midi(self):
        """初始化 pygame.midi，优先选用真正的合成器"""
        self.midi_available = False
        self.midi_output = None
        self.midi_device_name = ""

        try:
            import pygame.midi
            pygame.midi.init()
            device_count = pygame.midi.get_count()

            # 分类设备
            preferred = []   # 优先设备（GS Wavetable 等）
            others = []      # 其他设备
            skip_names = ["midi mapper"]  # 跳过：纯映射器，不能直接播放

            for i in range(device_count):
                try:
                    info = pygame.midi.get_device_info(i)
                    if not info:
                        continue
                    is_output = info[3]
                    if not is_output:
                        continue
                    raw_name = info[1]
                    try:
                        name = raw_name.decode("utf-8", errors="ignore")
                    except Exception:
                        name = str(raw_name)

                    name_lower = name.lower()

                    # 跳过 MIDI Mapper
                    if any(sk in name_lower for sk in skip_names):
                        continue

                    # 优先识别 GS Wavetable Synth / 含 "wavetable" 或 "synth" 的
                    if "wavetable" in name_lower or "gs" in name_lower or "synth" in name_lower:
                        preferred.append((i, name))
                    else:
                        others.append((i, name))
                except Exception:
                    continue

            # 按优先级尝试打开
            try_order = preferred + others
            for i, name in try_order:
                try:
                    self.midi_output = pygame.midi.Output(i)
                    self.midi_available = True
                    self.midi_device_name = name
                    break
                except Exception:
                    self.midi_output = None
                    continue

        except Exception:
            self.midi_available = False
            self.midi_output = None

    # ============================================================
    #  UI
    # ============================================================
    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=(10, 5))

        tk.Button(top, text="📁 加载 MIDI 文件", command=self.select_midi_file,
                  bg="#4A90E2", fg="white",
                  font=("微软雅黑", 10, "bold"),
                  cursor="hand2", height=1).pack(side=tk.LEFT)

        self.lbl_file = tk.Label(top, text="尚未选择文件", fg="#666",
                                  font=("微软雅黑", 10))
        self.lbl_file.pack(side=tk.LEFT, padx=15)

        tk.Button(top, text="🔄 从 OutPut 加载最新", command=self.reload_from_output,
                  font=("微软雅黑", 9), cursor="hand2").pack(side=tk.LEFT, padx=5)

        ctrl = tk.Frame(self)
        ctrl.pack(fill=tk.X, padx=10, pady=5)

        tk.Button(ctrl, text="⏮ 回到起点", command=self.goto_start,
                  font=("微软雅黑", 9), width=12, cursor="hand2").pack(side=tk.LEFT, padx=3)

        self.btn_play = tk.Button(ctrl, text="▶ 播放", command=self.toggle_play,
                                   font=("微软雅黑", 10, "bold"), width=12,
                                   bg="#7ED321", fg="white", cursor="hand2")
        self.btn_play.pack(side=tk.LEFT, padx=3)

        tk.Button(ctrl, text="⏭ 回到终点", command=self.goto_end,
                  font=("微软雅黑", 9), width=12, cursor="hand2").pack(side=tk.LEFT, padx=3)

        self.lbl_time = tk.Label(ctrl, text="00:00 / 00:00",
                                  font=("Consolas", 11, "bold"), fg="#333")
        self.lbl_time.pack(side=tk.LEFT, padx=20)

        self.lbl_info = tk.Label(ctrl, text="", font=("微软雅黑", 9), fg="#666")
        self.lbl_info.pack(side=tk.LEFT, padx=10)

        self.lbl_status = tk.Label(ctrl, text="", font=("微软雅黑", 9), fg="#888")
        self.lbl_status.pack(side=tk.RIGHT)

        main_area = tk.Frame(self)
        main_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left_panel = tk.Frame(main_area, width=200, bg="#f8f8f8",
                               relief=tk.GROOVE, borderwidth=1)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        left_panel.pack_propagate(False)

        tk.Label(left_panel, text="轨道", font=("微软雅黑", 10, "bold"),
                 bg="#f8f8f8").pack(pady=8)

        self.track_list_canvas = tk.Canvas(left_panel, bg="#f8f8f8",
                                            highlightthickness=0)
        self.track_list_canvas.pack(fill=tk.BOTH, expand=True)

        right_panel = tk.Frame(main_area)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(right_panel, bg="white",
                                 highlightthickness=1,
                                 highlightbackground="#ccc")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        timeline_frame = tk.Frame(self, bg="#f0f0f0")
        timeline_frame.pack(fill=tk.X, padx=10, pady=(0, 3))

        tk.Label(timeline_frame, text="时间轴", font=("微软雅黑", 9),
                 fg="#666").pack(side=tk.LEFT, padx=(0, 8))

        self.timeline_canvas = tk.Canvas(timeline_frame, height=28,
                                          bg="#f0f0f0",
                                          highlightthickness=1,
                                          highlightbackground="#bbb",
                                          cursor="hand2")
        self.timeline_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.timeline_canvas.bind("<Button-1>", self._on_timeline_click)
        self.timeline_canvas.bind("<B1-Motion>", self._on_timeline_drag)

        scroll_frame = tk.Frame(self)
        scroll_frame.pack(fill=tk.X, padx=10, pady=5)
        self.h_scroll = ttk.Scrollbar(scroll_frame, orient=tk.HORIZONTAL,
                                       command=self._on_h_scroll)
        self.h_scroll.pack(fill=tk.X)

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.timeline_canvas.bind("<Configure>", lambda e: self._draw_timeline())

        # 显示 MIDI 设备状态
        self._update_midi_status()

    def _update_midi_status(self):
        if self.midi_available:
            self.lbl_status.config(
                text=f"✅ MIDI 设备：{self.midi_device_name}",
                fg="#006400")
        else:
            self.lbl_status.config(
                text="⚠️ 未检测到 MIDI 播放设备",
                fg="#c00")

    # ============================================================
    #  文件选择
    # ============================================================
    def select_midi_file(self):
        path = filedialog.askopenfilename(
            title="选择 MIDI 文件",
            filetypes=[("MIDI 文件", "*.mid *.midi"), ("所有文件", "*.*")])
        if path:
            self.load_midi(path)

    def reload_from_output(self):
        output_dir = Path(__file__).resolve().parent / "OutPut"
        if not output_dir.exists():
            messagebox.showinfo("提示", f"OutPut 文件夹不存在：\n{output_dir}")
            return
        mids = list(output_dir.glob("*.mid")) + list(output_dir.glob("*.midi"))
        if not mids:
            messagebox.showinfo("提示", "OutPut 文件夹里没有 MIDI 文件。")
            return
        mids.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        self.load_midi(str(mids[0]))

    # ============================================================
    #  加载 MIDI
    # ============================================================
    def load_midi(self, path):
        try:
            midi = pretty_midi.PrettyMIDI(path)
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取 MIDI 文件：\n{e}")
            return

        self.stop_playback()
        self.midi_path = path
        self.midi_data = midi
        self.lbl_file.config(text=Path(path).name)

        self.tracks = []
        color_idx = 0
        for i, inst in enumerate(midi.instruments):
            if not inst.notes:
                continue
            color = TRACK_COLORS[color_idx % len(TRACK_COLORS)]
            color_idx += 1

            track_name = inst.name.strip() if inst.name else ""
            if not track_name:
                track_name = f"Track {i+1}"

            inst_name = get_instrument_name(inst.program, inst.is_drum)

            self.tracks.append({
                "track_name": track_name,
                "instrument_name": inst_name,
                "is_drum": inst.is_drum,
                "program": inst.program,
                "notes": list(inst.notes),
                "color": color,
            })

        if not self.tracks:
            messagebox.showinfo("提示", "这个 MIDI 文件里没有音符。")
            return

        all_pitches = []
        for t in self.tracks:
            for n in t["notes"]:
                all_pitches.append(n.pitch)
        if all_pitches:
            self.pitch_min = max(0, min(all_pitches) - 2)
            self.pitch_max = min(127, max(all_pitches) + 2)
        else:
            self.pitch_min, self.pitch_max = 48, 84

        self.total_duration = max(0.5, midi.get_end_time())
        self.scroll_offset = 0.0
        self.playback_position = 0.0

        self._extract_time_info()
        self._update_midi_status()

        self.after(200, self._post_load)

    def _extract_time_info(self):
        try:
            tempo_times, tempos = self.midi_data.get_tempo_changes()
            self.bpm = float(tempos[0]) if len(tempos) > 0 else 120.0
        except Exception:
            self.bpm = 120.0

        try:
            ts_changes = self.midi_data.time_signature_changes
            if ts_changes:
                self.time_signature = (ts_changes[0].numerator,
                                        ts_changes[0].denominator)
            else:
                self.time_signature = (4, 4)
        except Exception:
            self.time_signature = (4, 4)

        try:
            self.downbeats = list(self.midi_data.get_downbeats())
        except Exception:
            self.downbeats = []

        num, denom = self.time_signature
        self.lbl_info.config(
            text=f"BPM: {self.bpm:.1f}  |  拍号: {num}/{denom}  |  "
                 f"小节数: {len(self.downbeats)}")

    def _post_load(self):
        self._update_scrollbar()
        self._rebuild_track_labels()
        self._redraw()
        self._draw_timeline()
        self._update_time_label()

    def _rebuild_track_labels(self):
        self.track_list_canvas.delete("all")
        y = 10
        for t in self.tracks:
            self.track_list_canvas.create_rectangle(
                8, y + 6, 22, y + 20, fill=t["color"], outline="#666")

            display_track = t["track_name"]
            if t["is_drum"]:
                display_track = "🥁 " + display_track

            self.track_list_canvas.create_text(
                30, y + 4, text=display_track, anchor=tk.NW,
                font=("微软雅黑", 9, "bold"), fill="#222")

            self.track_list_canvas.create_text(
                30, y + 20, text=t["instrument_name"], anchor=tk.NW,
                font=("微软雅黑", 8), fill="#888")

            self.track_list_canvas.create_line(
                5, y + 38, 195, y + 38, fill="#ddd")

            y += 44

    # ============================================================
    #  滚动
    # ============================================================
    def _visible_duration(self):
        w = self.canvas.winfo_width()
        if w <= 1:
            w = 600
        return w / self.pixels_per_second

    def _update_scrollbar(self):
        if self.total_duration <= 0:
            return
        visible = self._visible_duration()
        if self.total_duration > visible:
            max_offset = self.total_duration - visible
            frac = self.scroll_offset / max_offset if max_offset > 0 else 0
            frac = max(0.0, min(1.0, frac))
            self.h_scroll.set(frac, min(1.0, frac + visible / self.total_duration))
        else:
            self.h_scroll.set(0, 1.0)

    def _on_h_scroll(self, *args):
        if self.total_duration <= 0:
            return
        visible = self._visible_duration()
        max_offset = max(0, self.total_duration - visible)

        if args[0] == "moveto":
            frac = float(args[1])
            self.scroll_offset = frac * max_offset
        elif args[0] == "scroll":
            amount = int(args[1])
            what = args[2]
            if what == "units":
                self.scroll_offset += amount * 1.0
            elif what == "pages":
                self.scroll_offset += amount * visible
            self.scroll_offset = max(0, min(max_offset, self.scroll_offset))

        self._redraw()

    # ============================================================
    #  绘制
    # ============================================================
    def _semitone_height(self):
        h = self.canvas.winfo_height()
        if h <= 1:
            h = 400
        pitch_range = self.pitch_max - self.pitch_min + 1
        if pitch_range <= 0:
            return 8
        return max(3, min(20, (h - 30) // pitch_range))

    def _redraw(self):
        self.canvas.delete("all")

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return

        if not self.tracks:
            self.canvas.create_text(w // 2, h // 2,
                                     text="请点击左上角「📁 加载 MIDI 文件」",
                                     font=("微软雅黑", 14), fill="#999")
            return

        sh = self._semitone_height()
        t_start = self.scroll_offset

        for i, db in enumerate(self.downbeats):
            x = (db - t_start) * self.pixels_per_second
            if -50 <= x <= w + 50:
                self.canvas.create_line(x, 0, x, h, fill="#c8c8c8", width=2)
                if 0 <= x <= w - 30:
                    self.canvas.create_text(
                        x + 4, 10, text=f"{i+1}",
                        font=("Consolas", 9, "bold"),
                        fill="#666", anchor=tk.W)

        try:
            num, denom = self.time_signature
            seconds_per_beat = 60.0 / self.bpm * (4.0 / denom)
            for db in self.downbeats:
                for b in range(1, num):
                    beat_t = db + b * seconds_per_beat
                    x = (beat_t - t_start) * self.pixels_per_second
                    if 0 <= x <= w:
                        self.canvas.create_line(x, 0, x, h,
                                                 fill="#f5f5f5", width=1)
        except Exception:
            pass

        note_names = ["C", "C#", "D", "D#", "E", "F",
                      "F#", "G", "G#", "A", "A#", "B"]
        for pitch in range(self.pitch_min, self.pitch_max + 1):
            if pitch % 12 == 0:
                y = (self.pitch_max - pitch) * sh
                if 0 <= y <= h:
                    self.canvas.create_line(0, y, w, y, fill="#e8e8e8", width=1)
                    name = note_names[pitch % 12]
                    octave = pitch // 12 - 1
                    self.canvas.create_text(3, y + 2,
                                             text=f"{name}{octave}",
                                             font=("Consolas", 7),
                                             fill="#aaa", anchor=tk.NW)

        for t in self.tracks:
            for note in t["notes"]:
                x1 = (note.start - t_start) * self.pixels_per_second
                x2 = (note.end - t_start) * self.pixels_per_second
                if x2 < 0 or x1 > w:
                    continue
                y = (self.pitch_max - note.pitch) * sh
                y1, y2 = y, y + sh - 1
                if x1 < 0:
                    x1 = 0
                if x2 > w:
                    x2 = w
                self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=t["color"], outline="#333", width=1)

        px = (self.playback_position - t_start) * self.pixels_per_second
        if 0 <= px <= w:
            self.canvas.create_line(px, 0, px, h, fill="#ff0000", width=2)

    # ============================================================
    #  底部时间轴
    # ============================================================
    def _draw_timeline(self):
        c = self.timeline_canvas
        c.delete("all")

        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1 or h <= 1:
            return

        if self.total_duration <= 0:
            c.create_text(w // 2, h // 2, text="（未加载 MIDI）",
                          font=("微软雅黑", 9), fill="#999")
            return

        c.create_rectangle(0, 0, w, h, fill="#e0e0e0", outline="")

        progress_x = int(w * (self.playback_position / self.total_duration))
        progress_x = max(0, min(w, progress_x))
        c.create_rectangle(0, 0, progress_x, h, fill="#a0d0ff", outline="")

        try:
            total_bars = len(self.downbeats)
            if total_bars > 0:
                step = max(1, total_bars // 20)
                for i in range(0, total_bars, step):
                    db = self.downbeats[i]
                    x = int(w * db / self.total_duration)
                    c.create_line(x, 0, x, 6, fill="#888")
                for i in range(0, total_bars, step * 2):
                    db = self.downbeats[i]
                    x = int(w * db / self.total_duration)
                    if 20 <= x <= w - 20:
                        c.create_text(x, h - 6, text=str(i + 1),
                                       font=("Consolas", 8), fill="#555")
        except Exception:
            pass

        c.create_line(progress_x, 0, progress_x, h, fill="#ff0000", width=2)
        c.create_polygon(
            progress_x - 5, 0, progress_x + 5, 0, progress_x, 6,
            fill="#ff0000", outline="")

    def _on_timeline_click(self, event):
        self._seek_timeline(event.x)

    def _on_timeline_drag(self, event):
        self._seek_timeline(event.x)

    def _seek_timeline(self, x):
        if self.total_duration <= 0:
            return
        w = self.timeline_canvas.winfo_width()
        if w <= 1:
            return
        frac = max(0.0, min(1.0, x / w))
        self.playback_position = frac * self.total_duration

        if self.is_playing:
            self.stop_playback()
            self.start_playback()
        else:
            self._redraw()
            self._draw_timeline()
            self._update_time_label()

    # ============================================================
    #  画布点击
    # ============================================================
    def _on_canvas_click(self, event):
        if self.total_duration <= 0:
            return
        click_time = self.scroll_offset + event.x / self.pixels_per_second
        click_time = max(0.0, min(self.total_duration, click_time))
        self.playback_position = click_time

        if self.is_playing:
            self.stop_playback()
            self.start_playback()
        else:
            self._redraw()
            self._draw_timeline()
            self._update_time_label()

    def goto_start(self):
        self.playback_position = 0.0
        if self.is_playing:
            self.stop_playback()
            self.start_playback()
        else:
            self._redraw()
            self._draw_timeline()
            self._update_time_label()

    def goto_end(self):
        self.playback_position = max(0.0, self.total_duration - 0.3)
        if self.is_playing:
            self.stop_playback()
            self.start_playback()
        else:
            self._redraw()
            self._draw_timeline()
            self._update_time_label()

    # ============================================================
    #  播放
    # ============================================================
    def toggle_play(self):
        if self.is_playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self):
        if not self.tracks:
            messagebox.showinfo("提示", "请先加载 MIDI 文件。")
            return
        if not self.midi_available or self.midi_output is None:
            messagebox.showwarning("无法播放",
                                    "未检测到 MIDI 播放设备。\n\n"
                                    "你的电脑上可能缺少 MIDI 合成器。\n\n"
                                    "你仍然可以查看音符，只是暂时无法播放。")
            return

        self.is_playing = True
        self.btn_play.config(text="⏸ 停止", bg="#F5A623")
        self.play_start_time = time.time()
        self.play_start_offset = self.playback_position

        threading.Thread(target=self._playback_loop, daemon=True).start()
        self._update_playhead()

    def stop_playback(self):
        self.is_playing = False
        self.btn_play.config(text="▶ 播放", bg="#7ED321")
        if self.midi_output is not None:
            try:
                for ch in range(16):
                    self.midi_output.write_short(0xB0 | ch, 123, 0)
            except Exception:
                pass

    def _playback_loop(self):
        events = []
        for t in self.tracks:
            for n in t["notes"]:
                events.append((n.start, "on", n.pitch, n.velocity,
                               t["program"], t["is_drum"]))
                events.append((n.end, "off", n.pitch, 0,
                               t["program"], t["is_drum"]))
        events.sort(key=lambda x: x[0])

        start_offset = self.play_start_offset
        start_wall = time.time()
        pitch_channel = {}

        for ev in events:
            if not self.is_playing:
                break
            ev_time, ev_type, pitch, velocity, program, is_drum = ev
            if ev_time < start_offset:
                continue

            target_elapsed = ev_time - start_offset
            while self.is_playing:
                if time.time() - start_wall >= target_elapsed:
                    break
                time.sleep(0.005)
            if not self.is_playing:
                break

            try:
                ch = 9 if is_drum else 0
                if not is_drum:
                    self.midi_output.set_instrument(program, ch)
                if ev_type == "on":
                    self.midi_output.note_on(pitch, velocity, ch)
                    pitch_channel[pitch] = ch
                else:
                    c = pitch_channel.pop(pitch, ch)
                    self.midi_output.note_off(pitch, 0, c)
            except Exception:
                pass

        if self.midi_output is not None:
            try:
                for ch in range(16):
                    self.midi_output.write_short(0xB0 | ch, 123, 0)
            except Exception:
                pass

        if self.is_playing:
            self.is_playing = False
            self.after(0, lambda: self.btn_play.config(
                text="▶ 播放", bg="#7ED321"))

    def _update_playhead(self):
        if not self.is_playing:
            return
        elapsed = time.time() - self.play_start_time
        self.playback_position = self.play_start_offset + elapsed

        if self.playback_position >= self.total_duration:
            self.playback_position = self.total_duration
            self.stop_playback()
            self._redraw()
            self._draw_timeline()
            self._update_time_label()
            return

        visible = self._visible_duration()
        if self.playback_position > self.scroll_offset + visible * 0.85:
            self.scroll_offset = self.playback_position - visible * 0.5
            self._update_scrollbar()

        self._redraw()
        self._draw_timeline()
        self._update_time_label()
        self.after(50, self._update_playhead)

    def _update_time_label(self):
        cur = self.playback_position
        total = self.total_duration
        cur_str = f"{int(cur // 60):02d}:{int(cur % 60):02d}"
        tot_str = f"{int(total // 60):02d}:{int(total % 60):02d}"
        self.lbl_time.config(text=f"{cur_str} / {tot_str}")