# -*- coding: utf-8 -*-
"""子进程入口：接收 JSON 参数，执行单个文件的转换（UTF-8 强制版）"""
import sys, json, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    if len(sys.argv) < 2:
        print("[runner] 缺少参数")
        sys.exit(1)
    try:
        args = json.loads(sys.argv[1])
    except Exception as e:
        print(f"[runner] 参数解析失败: {e}")
        sys.exit(1)

    mode = args.get("mode", "3")
    file_path = Path(args["file"])
    device = args.get("device", "cuda")
    do_quantize = args.get("do_quantize", False)
    use_ext_sep = args.get("use_ext_sep", False)
    demucs_model = args.get("demucs_model", "htdemucs")
    force_bpm = args.get("force_bpm", None)

    # 拍号：JSON 里传的是 [numerator, denominator] 列表
    force_ts_raw = args.get("force_time_signature", None)
    force_time_signature = None
    if force_ts_raw is not None:
        try:
            force_time_signature = (int(force_ts_raw[0]), int(force_ts_raw[1]))
        except Exception:
            force_time_signature = None

    try:
        if mode == "3":
            import run_stem_pipeline as pipeline
            pipeline.process_one(file_path, device, progress_cb=None,
                                 do_quantize=do_quantize,
                                 use_external_sep=use_ext_sep,
                                 demucs_model=demucs_model,
                                 force_bpm=force_bpm,
                                 force_time_signature=force_time_signature)
        elif mode == "1":
            import run_gpu_pipeline as pipeline
            pipeline.process_one(file_path, device, progress_cb=None,
                                 do_quantize=do_quantize,
                                 force_bpm=force_bpm,
                                 force_time_signature=force_time_signature)
        else:
            import run_cpu_pipeline as pipeline
            pipeline.process_one(file_path, progress_cb=None,
                                 do_quantize=do_quantize,
                                 force_bpm=force_bpm,
                                 force_time_signature=force_time_signature)
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"\n[runner] 处理失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()