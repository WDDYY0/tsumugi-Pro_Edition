# -*- coding: utf-8 -*-
"""demucs 启动包装器：import demucs 前先 patch endpoint"""
import os, sys

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HUGGINGFACE_HUB_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "60"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

try:
    import huggingface_hub
    if hasattr(huggingface_hub, "constants"):
        try:
            huggingface_hub.constants.ENDPOINT = "https://hf-mirror.com"
        except Exception:
            pass
        try:
            huggingface_hub.constants.HF_ENDPOINT = "https://hf-mirror.com"
        except Exception:
            pass
    try:
        import huggingface_hub.constants as _c
        _c.ENDPOINT = "https://hf-mirror.com"
    except Exception:
        pass
except Exception:
    pass

sys.argv = ["demucs"] + sys.argv[1:]
try:
    from demucs.separate import main
    main()
except SystemExit:
    raise
except Exception as e:
    print(f"[demucs_runner] 运行失败: {e}")
    sys.exit(1)