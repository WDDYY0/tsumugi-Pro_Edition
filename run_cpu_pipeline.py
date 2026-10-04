# -*- coding: utf-8 -*-
"""模式2：强制CPU转换（两阶段尝试：原文件 → 失败则转码重试）"""
import subprocess, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_DIR = PROJECT_ROOT / "InPut"
OUTPUT_DIR = PROJECT_ROOT / "OutPut"
TEMP_DIR = PROJECT_ROOT / "temp_converted"
SPLIT_DIR = OUTPUT_DIR / "分轨文件"
sys.path.insert(0, str(PROJECT_ROOT))
import tsumugi_tools


def _do_core_pipeline(safe_audio: Path, audio_file: Path,
                      progress_cb, do_quantize, force_bpm,
                      force_time_signature) -> bool:
    if progress_cb:
        progress_cb(15, "AI 正在扒谱（请耐心等待）...")
    output_midi = OUTPUT_DIR / f"{audio_file.stem}.mid"
    result = subprocess.run(
        ["uv", "run", "python", "-m", "instrument_agnostic_amt.amt.cli.infer",
         "--audio", str(safe_audio), "--output-midi", str(output_midi),
         "--device", "cpu"],
        check=False)
    if result.returncode != 0:
        raise RuntimeError(f"模型推理失败，返回码: {result.returncode}")

    if force_bpm is not None:
        if progress_cb:
            progress_cb(75, f"正在固定 BPM 到 {force_bpm}...")
        bpm_midi = OUTPUT_DIR / f"{audio_file.stem}_BPM{int(force_bpm)}.mid"
        tsumugi_tools.force_bpm_to_midi(output_midi, bpm_midi, force_bpm)
        output_midi = bpm_midi

    if force_time_signature is not None:
        if progress_cb:
            progress_cb(78, f"正在设置拍号 {force_time_signature}...")
        num, denom = force_time_signature
        ts_midi = OUTPUT_DIR / f"{audio_file.stem}_拍号{num}-{denom}.mid"
        tsumugi_tools.force_time_signature_to_midi(output_midi, ts_midi, num, denom)
        output_midi = ts_midi

    final_midi_to_split = output_midi
    if do_quantize:
        if progress_cb:
            progress_cb(85, "正在自动量化...")
        quantized_midi = OUTPUT_DIR / f"{audio_file.stem}_量化.mid"
        tsumugi_tools.auto_quantize_midi(output_midi, quantized_midi)
        final_midi_to_split = quantized_midi
    else:
        if progress_cb:
            progress_cb(85, "跳过量化...")

    if progress_cb:
        progress_cb(90, "正在导出分轨 MIDI...")
    tsumugi_tools.split_tracks(final_midi_to_split, SPLIT_DIR / f"{audio_file.stem}_分轨", audio_file.stem)
    if progress_cb:
        progress_cb(100, "处理完成")
    print(f"\n[完成] 输出 MIDI: {output_midi}")
    return True


def process_one(audio_file: Path, progress_cb=None, do_quantize=False,
                force_bpm=None, force_time_signature=None) -> bool:
    print(f"\n{'=' * 60}\n  正在处理: {audio_file.name}\n  使用设备: cpu\n  "
          f"转换模式: 常规（仅扒谱）\n  手动BPM: {force_bpm if force_bpm else '未指定'}\n"
          f"  手动拍号: {force_time_signature if force_time_signature else '未指定'}\n{'=' * 60}\n")

    print(f"[阶段 1/2] 尝试直接用原文件 {audio_file.name} 处理...")
    if progress_cb:
        progress_cb(5, "准备音频（直接使用原文件）...")

    safe_audio = tsumugi_tools.check_and_convert_audio(audio_file, TEMP_DIR)

    try:
        return _do_core_pipeline(
            safe_audio=safe_audio, audio_file=audio_file,
            progress_cb=progress_cb, do_quantize=do_quantize,
            force_bpm=force_bpm, force_time_signature=force_time_signature,
        )
    except Exception as e:
        err_str = str(e)
        print(f"\n[阶段 1] ❌ 原文件处理失败：{err_str[:300]}")

        if not tsumugi_tools._is_decode_error(e):
            print(f"[阶段 2] 该错误与音频格式无关，不再尝试转码。")
            raise

        print(f"\n[阶段 2] 检测到解码问题，尝试转码为标准化 WAV 后重试...")

    if progress_cb:
        progress_cb(5, "转码为标准化 WAV...")

    try:
        converted_audio = tsumugi_tools.convert_to_standard_wav(audio_file, TEMP_DIR)
    except Exception as e:
        print(f"[阶段 2] ❌ 转码失败：{e}")
        raise RuntimeError(
            f"文件 {audio_file.name} 处理失败：\n"
            f"· 原文件无法直接解码\n"
            f"· 转码也失败了\n\n"
            f"原始错误：{e}"
        )

    print(f"[阶段 2] 转码成功，使用 {converted_audio.name} 重新尝试处理...")
    if progress_cb:
        progress_cb(8, "已转码为标准 WAV，开始处理...")

    try:
        return _do_core_pipeline(
            safe_audio=converted_audio, audio_file=audio_file,
            progress_cb=progress_cb, do_quantize=do_quantize,
            force_bpm=force_bpm, force_time_signature=force_time_signature,
        )
    except Exception as e:
        print(f"\n[阶段 2] ❌ 转码后处理仍失败：{e}")
        raise RuntimeError(
            f"文件 {audio_file.name} 处理失败：\n"
            f"· 原文件无法直接解码\n"
            f"· 转码后仍然失败\n\n"
            f"详细错误：{e}"
        )