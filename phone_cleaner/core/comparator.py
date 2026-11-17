import os
import struct
import hashlib
import subprocess
from typing import List, Optional

class VisualComparator:
    """
    视觉感知哈希与内容相似度比对器
    利用硬件级图像重采样与皮尔逊统计相关系数，能够高度稳健地识别同一张图片在经历
    JPEG压缩、重编码、小幅尺寸缩放或色彩空间转换后的视觉一致性
    """

    @staticmethod
    def compute_file_md5(file_path: str) -> Optional[str]:
        """计算本地文件的 MD5 摘要"""
        if not os.path.exists(file_path):
            return None
        hasher = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return None

    @staticmethod
    def get_fingerprint(img_path: str, size: int = 16) -> Optional[List[int]]:
        """
        利用 macOS sips 工具快速生成尺寸极小（16x16）的灰度像素特征指纹
        """
        if not os.path.exists(img_path):
            return None
        tmp_bmp = f"/tmp/sig_{os.path.basename(img_path)}.bmp"
        try:
            subprocess.run(
                ["/usr/bin/sips", "-s", "format", "bmp", "-z", str(size), str(size), img_path, "--out", tmp_bmp],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=5
            )
            with open(tmp_bmp, "rb") as f:
                data = f.read()
            if os.path.exists(tmp_bmp):
                os.remove(tmp_bmp)

            # 读取 BMP 像素数据区偏移 (字节 10~14)
            offset = struct.unpack("<I", data[10:14])[0]
            raw = data[offset:]
            grays = []
            for i in range(0, len(raw), 3):
                if i + 2 < len(raw):
                    b, g, r = raw[i], raw[i+1], raw[i+2]
                    grays.append(int(0.299 * r + 0.587 * g + 0.114 * b))
            return grays[: size * size]
        except Exception:
            if os.path.exists(tmp_bmp):
                os.remove(tmp_bmp)
            return None

    @classmethod
    def compute_similarity(cls, sig1: Optional[List[int]], sig2: Optional[List[int]]) -> float:
        """
        计算两个图像特征指纹的皮尔逊相关系数
        返回值范围：0.0 ~ 1.0 (1.0 代表像素分布完全一致)
        """
        if not sig1 or not sig2 or len(sig1) != len(sig2):
            return 0.0
        n = len(sig1)
        m1 = sum(sig1) / n
        m2 = sum(sig2) / n
        v1 = sum((x - m1) ** 2 for x in sig1)
        v2 = sum((y - m2) ** 2 for y in sig2)
        if v1 == 0 or v2 == 0:
            return 1.0 if sig1 == sig2 else 0.0
        cov = sum((x - m1) * (y - m2) for x, y in zip(sig1, sig2))
        score = cov / ((v1 * v2) ** 0.5)
        return max(0.0, min(1.0, score))

    @classmethod
    def is_same_image(cls, sig1: Optional[List[int]], sig2: Optional[List[int]], threshold: float = 0.88) -> bool:
        """判定两张图片是否为同一张视觉内容"""
        return cls.compute_similarity(sig1, sig2) >= threshold
