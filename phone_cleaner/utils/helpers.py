import os
import subprocess
from typing import Tuple
from phone_cleaner.config import ALLOWED_PHONE_ROOTS

def format_size(size_bytes: int) -> str:
    """人性化文件大小格式化"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def format_timestamp(ts: str) -> str:
    """格式化 yyyyMMdd_HHmmss 格式时间戳为可读文本"""
    if len(ts) >= 15 and ts[8] == '_':
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
    return ts

def get_image_dimensions(file_path: str) -> Tuple[int, int]:
    """通过 macOS 内置 sips 获取图片宽度与高度（分辨率）"""
    try:
        res = subprocess.run(
            ["/usr/bin/sips", "-g", "pixelWidth", "-g", "pixelHeight", file_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        w, h = 0, 0
        for line in res.stdout.splitlines():
            line = line.strip()
            if "pixelWidth:" in line:
                w = int(line.split(":")[-1].strip())
            elif "pixelHeight:" in line:
                h = int(line.split(":")[-1].strip())
        return w, h
    except Exception:
        return 0, 0

def convert_to_preview_jpg(src_path: str, dst_path: str) -> bool:
    """通过 macOS 内置 sips 转换 HEIC/INSP/DNG 格式为 Web 可直接展示的 JPEG"""
    try:
        subprocess.run(
            ["/usr/bin/sips", "-s", "format", "jpeg", src_path, "--out", dst_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=10
        )
        return True
    except Exception:
        return False

def is_safe_phone_path(phone_path: str) -> bool:
    """
    极严苛的路径安全检查
    必须以 /storage/emulated/0/ 为前缀，且不能包含非法字符或处于根路径
    """
    if not phone_path or not isinstance(phone_path, str):
        return False
    clean = os.path.normpath(phone_path.strip())
    if not clean.startswith("/storage/emulated/0/"):
        return False
    if clean == "/storage/emulated/0" or clean == "/storage/emulated/0/":
        return False
    if ".." in clean.split("/"):
        return False
    return True
