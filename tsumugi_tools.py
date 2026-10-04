# -*- coding: utf-8 -*-
"""公共工具包：格式兼容、显存自适应、MIDI量化、多轨拆分、固定BPM、固定拍号"""
import os
import shutil
import subprocess
from pathlib import Path
import pretty_midi
import torch

_PROJECT_ROOT = Path(__file__).resolve().parent
_INTERNAL_FFMPEG = _PROJECT_ROOT / "tools" / "ffmpeg" / "ffmpeg.exe"


def _find_ffmpeg() -> str:
    if _INTERNAL_FFMPEG.exists():
        return str(_INTERNAL_FFMPEG)
    ffmpeg_cmd = shutil.which("ffmpeg")
    if ffmpeg_cmd:
        return ffmpeg_cmd
    for p in [r"D:\ffmpeg\bin\ffmpeg.exe", r"C:\ffmpeg\bin\ffmpeg.exe"]:
        if Path(p).exists():
            return p
    return ""


def verify_audio_file(file_path: Path) -> bool:
    try:
        import soundfile as sf
        info = sf.info(str(file_path))
        if info.samplerate > 0 and info.frames > 0:
            return True
    except Exception:
        pass
    return False


def check_and_convert_audio(audio_path: Path, temp_dir: Path) -> Path:
    """
    不再预检、不再自动转码。直接返回原文件路径。
    失败重试逻辑由 pipeline 层负责。
    """
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError(f"文件不存在或为空: {audio_path.name}")
    return audio_path


def convert_to_standard_wav(audio_path: Path, temp_dir: Path) -> Path:
    """
    显式调用：将音频转码为 44.1kHz / 16bit / 双声道标准 WAV。
    只在原文件处理失败后由 pipeline 调用。
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path = temp_dir / f"{audio_path.stem}_std.wav"

    try:
        if output_path.exists() and output_path.stat().st_mtime >= audio_path.stat().st_mtime:
            if verify_audio_file(output_path):
                print(f"[音频转码] 复用已有缓存：{output_path.name}")
                return output_path
    except Exception:
        pass

    ffmpeg_cmd = _find_ffmpeg()
    if not ffmpeg_cmd:
        raise RuntimeError(
            "找不到 FFmpeg，无法转码音频。\n"
            "请确认项目目录下的 tools/ffmpeg/ffmpeg.exe 存在。"
        )

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        print(f"[音频转码] 正在将 {audio_path.name} 转码为标准 WAV "
              f"（第 {attempt} 次尝试）...")
        cmd = [
            ffmpeg_cmd, "-y", "-i", str(audio_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            str(output_path),
        ]
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                check=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip().splitlines()[-1] if e.stderr else "未知错误"
            print(f"[音频转码] 第 {attempt} 次失败: {err_msg}")
            if attempt == max_retries:
                raise RuntimeError(f"文件 {audio_path.name} 连续 3 次转码失败，可能不是有效的音频文件。")
            continue

        if verify_audio_file(output_path):
            print(f"[音频转码] ✅ 转码成功 → {output_path.name}")
            return output_path
        else:
            print(f"[音频转码] 转码后的文件为空或内容不是合法音频。")
            if attempt == max_retries:
                raise RuntimeError(f"文件 {audio_path.name} 转码后内容无效，可能不是音频。")

    return output_path


def _is_decode_error(err: Exception) -> bool:
    """判断异常是否与音频解码有关（决定要不要转码重试）"""
    keys = [
        "decode", "decoder", "torchcodec",
        "could not receive frame",
        "failed to decode audio",
        "invalid data found",
        "failed to create audiodecoder",
        "libtorchcodec",
        "could not load",
        "soundfile", "libsndfile",
        "format not recognised", "format not recognized",
        "audioread", "no backend", "nobackenderror",
        "unsupported format", "unsupported file",
        "error opening", "could not open",
        "unknown format",
        "m4a", "aac", "wma", "opus",
    ]

    # 检查主错误
    s = str(err).lower()
    if any(k in s for k in keys):
        return True

    # 检查异常链（__cause__ 和 __context__）
    for attr in ("__cause__", "__context__"):
        cause = getattr(err, attr, None)
        depth = 0
        while cause is not None and depth < 5:
            cs = str(cause).lower()
            if any(k in cs for k in keys):
                return True
            cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)
            depth += 1

    return False


def auto_adapt_low_vram() -> bool:
    try:
        if not torch.cuda.is_available():
            return False
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / (1024 ** 3)
        if vram_gb < 12:
            print(f"[显存自适应] 检测到显存 {vram_gb:.1f}GB（较小），自动开启低显存调度模式。")
            return True
        else:
            print(f"[显存自适应] 检测到显存 {vram_gb:.1f}GB（充裕），自动开启全速模式。")
            return False
    except Exception as e:
        print(f"[显存自适应] 检测出错，默认开启低显存模式。错误信息: {e}")
        return True


def auto_quantize_midi(input_midi: Path, output_midi: Path):
    try:
        midi = pretty_midi.PrettyMIDI(str(input_midi))
        try:
            bpm = midi.get_tempo_changes()[1][0]
        except Exception:
            bpm = 120.0
        beat_sec = 60.0 / bpm
        grid = beat_sec * 0.25
        for inst in midi.instruments:
            for note in inst.notes:
                note.start = round(note.start / grid) * grid
                note.end = round(note.end / grid) * grid
                if note.end <= note.start:
                    note.end = note.start + grid * 0.5
        midi.write(str(output_midi))
        print(f"[自动量化] 量化完成（统一 1/16 音符），已生成：{output_midi.name}")
    except Exception as e:
        print(f"[自动量化] 跳过，量化出错: {e}")


def force_bpm_to_midi(input_midi: Path, output_midi: Path, target_bpm: float):
    try:
        midi = pretty_midi.PrettyMIDI(str(input_midi))
        try:
            tempo_times, tempos = midi.get_tempo_changes()
            original_bpm = float(tempos[0]) if len(tempos) > 0 else 120.0
        except Exception:
            original_bpm = 120.0
        if original_bpm <= 0:
            original_bpm = 120.0
        scale = original_bpm / float(target_bpm)
        for inst in midi.instruments:
            for note in inst.notes:
                note.start *= scale
                note.end *= scale
            for cc in inst.control_changes:
                cc.time *= scale
            for pb in inst.pitch_bends:
                pb.time *= scale
        new_midi = pretty_midi.PrettyMIDI(initial_tempo=float(target_bpm))
        for inst in midi.instruments:
            new_midi.instruments.append(inst)
        try:
            new_midi.time_signature_changes = midi.time_signature_changes
        except Exception:
            pass
        try:
            new_midi.key_signature_changes = midi.key_signature_changes
        except Exception:
            pass
        new_midi.write(str(output_midi))
        print(f"[BPM] 原始 BPM：{original_bpm:.2f}，目标 BPM：{target_bpm}，"
              f"时间缩放比例：{scale:.4f}")
    except Exception as e:
        print(f"[BPM] 固定 BPM 失败: {e}")
        import traceback
        traceback.print_exc()
        shutil.copyfile(str(input_midi), str(output_midi))


def force_time_signature_to_midi(input_midi: Path, output_midi: Path,
                                  numerator: int, denominator: int):
    try:
        midi = pretty_midi.PrettyMIDI(str(input_midi))
        try:
            ts = pretty_midi.TimeSignature(numerator=int(numerator),
                                            denominator=int(denominator))
        except Exception:
            ts = pretty_midi.TimeSignature(int(numerator), int(denominator))
        try:
            ts.time = 0.0
        except Exception:
            pass
        midi.time_signature_changes = [ts]
        midi.write(str(output_midi))
        print(f"[拍号] 已设置拍号为 {numerator}/{denominator}")
    except Exception as e:
        print(f"[拍号] 设置拍号失败: {e}")
        import traceback
        traceback.print_exc()
        shutil.copyfile(str(input_midi), str(output_midi))


def split_tracks(input_midi: Path, output_dir: Path, song_name: str):
    try:
        midi = pretty_midi.PrettyMIDI(str(input_midi))
        output_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for i, inst in enumerate(midi.instruments):
            if not inst.notes:
                continue
            safe_name = "".join([c for c in inst.name if c.isalnum() or c in " _-"]).strip()
            if not safe_name:
                safe_name = f"Track_{i+1}"
            new_midi = pretty_midi.PrettyMIDI()
            new_inst = pretty_midi.Instrument(program=inst.program, is_drum=inst.is_drum, name=inst.name)
            new_inst.notes = inst.notes
            new_midi.instruments.append(new_inst)
            new_midi.write(str(output_dir / f"{song_name}_{safe_name}.mid"))
            count += 1
        print(f"[分轨导出] 已成功拆分为 {count} 个独立 MIDI 文件，保存在 {output_dir}")
    except Exception as e:
        print(f"[分轨导出] 失败: {e}")