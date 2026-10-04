import hashlib
import hmac
import base64
from pathlib import Path

_S1 = "dHN1bXVnaV8yMDI0X2ludGVn"
_S2 = "cmF0b3JfYW5pbWVfc29u"
_S3 = "Z19ieV93dWR1YW5fZGVf"
_S4 = "eXVleWluXyUkI0Ah"

# 收款码的内嵌签名（由 lock_qr.py 自动改写）
# 初始值全 0 表示尚未锁定
_EMBEDDED_SIG = "90cca8410fc40160738a539a68356a9e2f45a6d76ec2a87608debbdb2eba898e"


def _s():
    return base64.b64decode(_S1 + _S2 + _S3 + _S4)


def compute_signature(p):
    p = Path(p)
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        d = f.read()
    return hmac.new(_s(), d, hashlib.sha256).hexdigest()


def is_locked():
    return _EMBEDDED_SIG != "0" * 64


def verify_signature(image_path):
    i = Path(image_path)
    if not i.exists():
        return "missing_image", ""
    if not is_locked():
        return "no_signature", ""
    actual = compute_signature(i)
    if not actual:
        return "tampered", ""
    if hmac.compare_digest(_EMBEDDED_SIG, actual):
        return "ok", ""
    return "tampered", ""


def save_signature(image_path, sig_path=None):
    return False


compute_signature = compute_signature
verify_signature = verify_signature