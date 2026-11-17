import os
import shutil
from pathlib import Path

# 获取工作区目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 临时图片缓存与索引路径
DEFAULT_DATA_DIR = BASE_DIR / "temp_images"
DEFAULT_MANIFEST_PATH = DEFAULT_DATA_DIR / "manifest.json"

# Web 服务配置
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8899

# 图像比对配置
# 视觉相似度阈值（>= 0.88 判定为同一张图的缩略图/衍生图/跨目录重复）
DEFAULT_SIMILARITY_THRESHOLD = 0.88

# 手机端安全根目录白名单（严禁在此范围外删除文件）
ALLOWED_PHONE_ROOTS = [
    "/storage/emulated/0/DCIM",
    "/storage/emulated/0/Pictures",
    "/storage/emulated/0/Download",
    "/storage/emulated/0/MIUI",
    "/storage/emulated/0/Android/data/com.tencent.mobileqq",
    "/storage/emulated/0/Android/data/com.tencent.mm",
    "/storage/emulated/0/.$recycle_bin$"
]

# 常见图片扩展名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".dng", ".insp"}

def find_adb_binary() -> str:
    """自动探测系统中可用的 adb 二进制路径"""
    # 1. 检查环境变量
    env_adb = os.environ.get("ADB_PATH")
    if env_adb and os.path.exists(env_adb):
        return env_adb

    # 2. 检查 PATH
    which_adb = shutil.which("adb")
    if which_adb:
        return which_adb

    # 3. 常见系统安装路径
    candidates = [
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/opt/homebrew/Caskroom/android-platform-tools/36.0.0/platform-tools/adb",
        "/usr/bin/adb"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
            
    return "adb"
