# -*- coding: utf-8 -*-
"""模式3：超高精度分轨识别（两阶段尝试：原文件 → 失败则转码重试）"""
import shutil, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from instrument_agnostic_amt.cli.infer_stem import (
    run_stem_separated_transcription, merge_midis_logic, resolve_stem_model_type,
    get_stem_pipeline_models, _move_model,
)
from instrument_agnostic_amt.amt.cli import infer
from instrument_agnostic_amt.runtime import resolve_device
import tsumugi_tools
import advanced_separation

INPUT_DIR = PROJECT_ROOT / "InPut"
OUTPUT_DIR = PROJECT_ROOT / "OutPut"
STEM_OUTPUT_ROOT = PROJECT_ROOT / "stem_outputs"
TEMP_DIR = PROJECT_ROOT / "temp_converted"
SPLIT_DIR = OUTPUT_DIR / "分轨文件"
EXTERNAL_STEM_DIR = PROJECT_ROOT / "external_stems"


def _transcribe_external_stems(stems, audio_stem, device, low_vram, progress_cb=None):
    device = resolve_device(device)
    stem_midi_dir = STEM_OUTPUT_ROOT / audio_stem / "external_stem_midis"
    stem_midi_dir.mkdir(parents=True, exist_ok=True)
    midi_paths = []
    stem_names = list(stems.keys())
    for idx, (stem_name, stem_path) in enumerate(stems.items(), 1):
        model_type = resolve_stem_model_type(stem_name)
        if progress_cb:
            progress_cb(f"正在转写 {stem_name}（{idx}/{len(stem_names)}）...")
        print(f"[外部分离] 正在转写 stem: {stem_name} (model={model_type})")
        bundle = get_stem_pipeline_models(
            checkpoint_path=None, device_preference=device, model_type=model_type,
            low_vram_mode=low_vram, stem_splitter_batch_size=1, semi_crf_backend="torch",
        )
        amt_model = bundle["amt_model"]
        amt_forward = bundle["amt_forward"]
        amt_config = bundle["amt_config"]
        amt_settings = bundle["amt_settings"]
        if low_vram:
            _move_model(amt_model, device)
        try:
            allowed_ids = infer.resolve_stem_instrument_class_ids(stem_name)
            allowed_ids = infer.filter_supported_instrument_class_ids(
                allowed_ids, num_model_classes=amt_config.num_instrument_classes)
            waveform, _, _ = infer._load_audio(Path(stem_path), target_sample_rate=int(amt_config.sample_rate))
            notes, _, _ = infer.run_inference(
                model=amt_model, forward_model=amt_forward,
                waveform=waveform.to(device), model_config=amt_config,
                settings=amt_settings, device=device,
                amp_enabled=False, amp_dtype=None, velocity=100, merge_gap_ms=None,
                merge_onset_ms=20.0, silence_gate_rms_dbfs=-72,
                window_batch_size=2 if low_vram else 4,
                max_midi_melodic_instruments=15, disable_tqdm=True,
                max_note_seconds=15.0, allowed_instrument_ids=allowed_ids,
            )
            midi_obj = infer._build_midi(notes, sample_rate=amt_config.sample_rate)
            midi_out = stem_midi_dir / f"{audio_stem}_{stem_name}.mid"
            midi_obj.write(str(midi_out))
            midi_paths.append(midi_out)
        finally:
            if low_vram:
                _move_model(amt_model, "cpu")
    return midi_paths


def _do_core_pipeline(safe_audio: Path, audio_file: Path, device: str,
                      progress_cb, do_quantize, use_external_sep,
                      demucs_model, force_bpm, force_time_signature) -> bool:
    low_vram = tsumugi_tools.auto_adapt_low_vram()

    if use_external_sep:
        if progress_cb:
            progress_cb(8, "使用 demucs 精细分离中...")
        ext_dir = EXTERNAL_STEM_DIR / audio_file.stem
        if ext_dir.exists():
            shutil.rmtree(ext_dir)
        stems = advanced_separation.separate_with_demucs(
            safe_audio, ext_dir, model=demucs_model,
            progress_cb=lambda t: progress_cb(15, t) if progress_cb else None)
        if progress_cb:
            progress_cb(45, "外部分离完成，开始逐轨转写 MIDI...")
        stem_midi_paths = _transcribe_external_stems(stems, audio_file.stem, device, low_vram, progress_cb)
        if not stem_midi_paths:
            raise RuntimeError("外部分离后未生成任何 MIDI")
        if progress_cb:
            progress_cb(75, "正在合并所有分轨 MIDI...")
        merged_dir = STEM_OUTPUT_ROOT / audio_file.stem / "merged_external"
        merged_dir.mkdir(parents=True, exist_ok=True)
        merged_midi = merged_dir / f"{audio_file.stem}_merged.mid"
        merge_midis_logic(stem_midi_paths, merged_midi, max_melodic_instruments=15)
    else:
        if progress_cb:
            progress_cb(10, "AI 正在分离声部（这步最耗时，请耐心等待）...")
        result = run_stem_separated_transcription(
            audio_path=safe_audio, output_root=str(STEM_OUTPUT_ROOT), low_vram_mode=low_vram,
            stem_splitter_batch_size=1, window_batch_size=2 if low_vram else 4,
            refine_instruments=True, predict_velocity=True, predict_beat_chord=True,
            max_midi_melodic_instruments=15, merge_onset_ms=20.0, transcribe_drum_stems=True,
            cleanup_separated_stems=False, device=device)
        if progress_cb:
            progress_cb(75, "MIDI 转写完成，正在生成多轨文件...")
        merged_midi = Path(result["merged_midi_path"])
        if not merged_midi.exists():
            raise RuntimeError(f"合并 MIDI 不存在: {merged_midi}")

    output_midi = OUTPUT_DIR / f"{audio_file.stem}_多轨.mid"
    shutil.copyfile(merged_midi, output_midi)

    if force_bpm is not None:
        if progress_cb:
            progress_cb(80, f"正在固定 BPM 到 {force_bpm}...")
        bpm_midi = OUTPUT_DIR / f"{audio_file.stem}_多轨_BPM{int(force_bpm)}.mid"
        tsumugi_tools.force_bpm_to_midi(output_midi, bpm_midi, force_bpm)
        output_midi = bpm_midi

    if force_time_signature is not None:
        if progress_cb:
            progress_cb(82, f"正在设置拍号 {force_time_signature}...")
        num, denom = force_time_signature
        ts_midi = OUTPUT_DIR / f"{audio_file.stem}_多轨_拍号{num}-{denom}.mid"
        tsumugi_tools.force_time_signature_to_midi(output_midi, ts_midi, num, denom)
        output_midi = ts_midi

    final_midi_to_split = output_midi
    if do_quantize:
        if progress_cb:
            progress_cb(85, "正在自动量化...")
        quantized_midi = OUTPUT_DIR / f"{audio_file.stem}_多轨_量化.mid"
        tsumugi_tools.auto_quantize_midi(output_midi, quantized_midi)
        final_midi_to_split = quantized_midi
    else:
        if progress_cb:
            progress_cb(85, "跳过量化...")

    if progress_cb:
        progress_cb(95, "正在导出分轨 MIDI...")
    tsumugi_tools.split_tracks(final_midi_to_split, SPLIT_DIR / f"{audio_file.stem}_分轨", audio_file.stem)
    if progress_cb:
        progress_cb(100, "处理完成")
    print(f"\n[完成] 输出 MIDI: {output_midi}")
    return True


def process_one(audio_file: Path, device: str, progress_cb=None, do_quantize=False,
                use_external_sep: bool = False, demucs_model: str = "htdemucs",
                force_bpm=None, force_time_signature=None) -> bool:
    print(f"\n{'=' * 60}\n  正在处理: {audio_file.name}\n  使用设备: {device}\n  "
          f"精度模式: 最高（分轨+重分类+力度+拍号和弦）\n"
          f"  手动BPM: {force_bpm if force_bpm else '未指定'}\n"
          f"  手动拍号: {force_time_signature if force_time_signature else '未指定'}\n"
          f"{'=' * 60}\n")

    # 第一阶段：直接用原文件
    print(f"[阶段 1/2] 尝试直接用原文件 {audio_file.name} 处理...")
    if progress_cb:
        progress_cb(5, "准备音频（直接使用原文件）...")

    safe_audio = tsumugi_tools.check_and_convert_audio(audio_file, TEMP_DIR)

    try:
        return _do_core_pipeline(
            safe_audio=safe_audio, audio_file=audio_file, device=device,
            progress_cb=progress_cb, do_quantize=do_quantize,
            use_external_sep=use_external_sep, demucs_model=demucs_model,
            force_bpm=force_bpm, force_time_signature=force_time_signature,
        )
    except Exception as e:
        err_str = str(e)
        print(f"\n[阶段 1] ❌ 原文件处理失败：{err_str[:300]}")

        if not tsumugi_tools._is_decode_error(e):
            print(f"[阶段 2] 该错误与音频格式无关，不再尝试转码。")
            raise

        print(f"\n[阶段 2] 检测到解码问题，尝试转码为标准化 WAV 后重试...")

    # 第二阶段：转码后重试
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
            safe_audio=converted_audio, audio_file=audio_file, device=device,
            progress_cb=progress_cb, do_quantize=do_quantize,
            use_external_sep=use_external_sep, demucs_model=demucs_model,
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