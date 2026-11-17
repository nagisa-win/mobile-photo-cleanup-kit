import re
from typing import List, Dict, Any
from phone_cleaner.config import DEFAULT_SIMILARITY_THRESHOLD
from phone_cleaner.core.comparator import VisualComparator

EXACT_IMG_PATTERN = re.compile(r"^IMG_\d{8}_\d{6}\.[a-zA-Z0-9]+$", re.IGNORECASE)
TIMESTAMP_SUFFIX_PATTERN = re.compile(r"IMG_\d{8}_\d{6}_\d+", re.IGNORECASE)

class ImageClassifier:
    """
    智能图片角色分类器
    结合手机路径语义、文件命名规约与图像视觉指纹比对，精准判定：
    1. 原图 (Original) -> 推荐保留
    2. 真实缩略图/缓存 (Thumbnail/Cache) -> 确认同一图片，推荐删除
    3. 跨目录重复 (Duplicate) -> 确认同一图片，推荐删除
    4. 独立照片 (Independent) -> 仅同名但内容不同，强制保护不删除
    """

    @classmethod
    def select_best_original(cls, file_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """在一组候选图片中甄选最符合基准原图的文件"""
        candidates = []
        for fe in file_entries:
            is_std = bool(EXACT_IMG_PATTERN.match(fe["filename"]))
            is_qq = "com.tencent.mobileqq" in fe["phone_path"]
            if is_std and not is_qq:
                candidates.append(fe)

        if candidates:
            def rank_fn(item):
                score = 0
                if "/DCIM/Camera/" in item["phone_path"]:
                    score += 100000000
                elif "/Pictures/" in item["phone_path"]:
                    score += 50000000
                score += (item.get("width", 0) * item.get("height", 0))
                return score
            return max(candidates, key=rank_fn)
        elif file_entries:
            return max(file_entries, key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("size_bytes", 0)))
        return file_entries[0]

    @classmethod
    def classify_group(
        cls,
        file_entries: List[Dict[str, Any]],
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ) -> Dict[str, Any]:
        """对一组同时间戳的图片文件执行完整分类打标与视觉一致性验证"""
        if not file_entries:
            return {"files": [], "badges": []}

        best_orig = cls.select_best_original(file_entries)
        best_orig_id = best_orig["id"]
        orig_sig = VisualComparator.get_fingerprint(best_orig["local_path"])

        has_thumbnail = False
        has_qq = False
        has_confirmed_duplicate = False
        has_different_content = False

        for fe in file_entries:
            is_qq = "com.tencent.mobileqq" in fe["phone_path"]
            is_std = bool(EXACT_IMG_PATTERN.match(fe["filename"]))

            if fe["id"] == best_orig_id:
                fe["role"] = "original"
                fe["tag"] = "原图 · 推荐保留"
                fe["tag_short"] = "基准原图"
                fe["tag_color"] = "green"
                fe["similarity"] = 1.0
                fe["similarity_str"] = "100%"
                fe["is_same_image"] = True
                fe["reason"] = "标准格式命名、最高分辨率原始相片"
                fe["auto_select"] = False
                continue

            # 视觉相似度比对
            cur_sig = VisualComparator.get_fingerprint(fe["local_path"])
            sim = VisualComparator.compute_similarity(orig_sig, cur_sig)
            fe["similarity"] = round(sim, 3)
            fe["similarity_str"] = f"{sim * 100:.1f}%"

            # 阈值判定
            is_same_content = (sim >= similarity_threshold)
            fe["is_same_image"] = is_same_content

            if not is_same_content:
                # 【核心保护规则】虽同名但内容完全不同，绝对不当成重复图！
                fe["role"] = "independent"
                fe["tag"] = "独立相片 · 内容不同"
                fe["tag_short"] = "独立相片 (已保护)"
                fe["tag_color"] = "blue"
                fe["reason"] = f"视觉相似度仅 {sim*100:.1f}%，确认为独立拍摄相片，已自动解除勾选保护"
                fe["auto_select"] = False
                has_different_content = True
            elif is_qq:
                if "/thumb/" in fe["phone_path"]:
                    fe["role"] = "thumbnail"
                    fe["tag"] = "QQ低清缩略图"
                    fe["tag_short"] = "QQ缩略图"
                    fe["tag_color"] = "red"
                    fe["reason"] = f"与原图匹配度 {sim*100:.0f}%，QQ压缩生成的低清缩略图 ({fe['resolution_str']})"
                else:
                    fe["role"] = "cache"
                    fe["tag"] = "QQ临时图片缓存"
                    fe["tag_short"] = "QQ图片缓存"
                    fe["tag_color"] = "orange"
                    fe["reason"] = f"与原图匹配度 {sim*100:.0f}%，QQ临时聊天图片缓存 ({fe['size_str']})"
                fe["auto_select"] = True
                has_qq = True
                has_thumbnail = True
            elif not is_std:
                fe["role"] = "thumbnail"
                fe["tag"] = "衍生压缩缩略图"
                fe["tag_short"] = "衍生缩略图"
                fe["tag_color"] = "red"
                fe["reason"] = f"与原图匹配度 {sim*100:.0f}%，含有多余时间戳后缀且被压缩 ({fe['size_str']})"
                fe["auto_select"] = True
                has_thumbnail = True
            else:
                # 跨目录同名，且【视觉内容确实相同 (sim >= 88%)】
                fe["role"] = "duplicate"
                fe["tag"] = "跨目录重复副本"
                fe["tag_short"] = "跨目录重复"
                fe["tag_color"] = "yellow"
                fe["reason"] = f"与原图匹配度 {sim*100:.0f}%，同一相片的跨目录重复存放 ({fe['size_str']})"
                fe["auto_select"] = True
                has_confirmed_duplicate = True

        badges = []
        if has_thumbnail:
            badges.append({"name": "含缩略图", "color": "red"})
        if has_qq:
            badges.append({"name": "含QQ缓存", "color": "orange"})
        if has_confirmed_duplicate:
            badges.append({"name": "确认重复图", "color": "yellow"})
        if has_different_content:
            badges.append({"name": "含同名不同图(已保护)", "color": "blue"})
        if not badges:
            badges.append({"name": "对比展示", "color": "slate"})

        return {
            "files": file_entries,
            "badges": badges,
            "has_different_content": has_different_content,
            "has_real_duplicate": (has_thumbnail or has_qq or has_confirmed_duplicate)
        }
