# -*- coding: utf-8 -*-
"""高级声源分离模块：封装 demucs 的安装、检测与调用"""
import subprocess, sys, os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

DEMUCS_MODELS = [
    ("htdemucs", "标准 4 轨（人声/鼓/贝斯/其他），推荐"),
    ("htdemucs_ft", "精调版 4 轨，质量更高，速度稍慢"),
    ("htdemucs_6s", "6 轨（额外分离吉他/钢琴），实验性"),
]


def _safe_print(text: str):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
    sys.stdout.flush()


def is_demucs_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("demucs") is not None
    except Exception:
        return False


def install_demucs() -> tuple:
    try:
        _safe_print("[高级分离] 正在安装 demucs（首次安装约 200MB，请耐心等待）...")
        result = subprocess.run(
            ["uv", "pip", "install", "demucs"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=900,
            encoding="utf-8", errors="replace")
        if result.returncode == 0:
            return True, "demucs 安装成功！"
        return False, f"安装失败：{result.stderr[-500:] if result.stderr else '未知错误'}"
    except subprocess.TimeoutExpired:
        return False, "安装超时，请检查网络后重试。"
    except Exception as e:
        return False, f"安装出错：{e}"


def separate_with_demucs(audio_path: Path, output_dir: Path,
                          model: str = "htdemucs", progress_cb=None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = Path(audio_path)
    if progress_cb:
        progress_cb("正在调用 demucs 进行精细分离...")

    runner_script = PROJECT_ROOT / "demucs_runner.py"
    if runner_script.exists():
        cmd = [sys.executable, str(runner_script), "-n", model, "-o", str(output_dir), str(audio_path)]
    else:
        cmd = [sys.executable, "-m", "demucs", "-n", model, "-o", str(output_dir), str(audio_path)]

    _safe_print(f"[高级分离] 执行命令: {' '.join(cmd)}")
    _safe_print(f"[高级分离] 已启用国内镜像（hf-mirror.com），下方会显示实时进度...")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["HF_HUB_ENDPOINT"] = "https://hf-mirror.com"
    env["HUGGINGFACE_HUB_ENDPOINT"] = "https://hf-mirror.com"

    try:
        process = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace",
                                   bufsize=1, env=env)
    except Exception as e:
        raise RuntimeError(f"无法启动 demucs 进程：{e}")

    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            clean = line.rstrip("\r\n")
            if clean:
                try:
                    clean_safe = clean.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
                except Exception:
                    clean_safe = "[demucs] (输出包含无法显示的字符)"
                _safe_print(f"[demucs] {clean_safe}")
        process.wait()
    except UnicodeEncodeError as e:
        raise RuntimeError(f"读取 demucs 输出时编码错误：{e}")
    except Exception as e:
        raise RuntimeError(f"读取 demucs 输出时出错：{e}")

    if process.returncode != 0:
        raise RuntimeError(f"demucs 分离失败，退出码: {process.returncode}（请查看上方日志）")

    song_stem_dir = output_dir / model / audio_path.stem
    if not song_stem_dir.exists():
        alt_dir = output_dir / audio_path.stem / model
        if alt_dir.exists():
            song_stem_dir = alt_dir
        else:
            raise RuntimeError(f"找不到 demucs 的输出目录：{song_stem_dir}")

    stems = {}
    for wav_file in song_stem_dir.glob("*.wav"):
        stems[wav_file.stem] = wav_file
    if not stems:
        raise RuntimeError("demucs 未生成任何音轨文件，请检查音频是否有效。")

    _safe_print(f"[高级分离] ✅ demucs 分离完成，共生成 {len(stems)} 个音轨：{list(stems.keys())}")
    return stems