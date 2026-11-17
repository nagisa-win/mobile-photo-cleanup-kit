import os
import re
import json
import time
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Callable

from phone_cleaner.config import DEFAULT_DATA_DIR, DEFAULT_MANIFEST_PATH, DEFAULT_SIMILARITY_THRESHOLD
from phone_cleaner.core.adb import ADBClient
from phone_cleaner.core.classifier import ImageClassifier, EXACT_IMG_PATTERN
from phone_cleaner.utils.helpers import format_size, format_timestamp, get_image_dimensions, convert_to_preview_jpg
from phone_cleaner.utils.logger import Logger

IMG_TIMESTAMP_PATTERN = re.compile(r"IMG_(\d{8}_\d{6})")

class PhoneScanner:
    """手机相册全盘扫描、文件批量拉取、元数据抽取与视觉比对全流程引擎"""

    def __init__(
        self,
        adb_client: Optional[ADBClient] = None,
        data_dir: Optional[Path] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ):
        self.adb = adb_client or ADBClient()
        self.data_dir = Path(data_dir or DEFAULT_DATA_DIR)
        self.manifest_path = self.data_dir / "manifest.json"
        self.similarity_threshold = similarity_threshold

    def clean_cache(self):
        """清空本地拉取的临时图片目录"""
        if self.data_dir.exists():
            shutil.rmtree(self.data_dir, ignore_errors=True)

    def scan_candidate_groups(
        self,
        scan_path: str = "/storage/emulated/0",
        progress_cb: Optional[Callable[[str, int, int, str], None]] = None
    ) -> Dict[str, List[str]]:
        """全盘扫描手机内置存储，筛选同时间戳或具有缩略图/衍生特征的候选对比组"""
        if progress_cb:
            progress_cb("scanning", 0, 0, f"正在通过 ADB 扫描手机存储 ({scan_path})...")
        Logger.step("1/3", f"正在通过 ADB 扫描手机内置存储 ({scan_path}) 中的全部图片...")
        
        code, stdout, err = self.adb.shell(f"find {scan_path} -type f 2>/dev/null", timeout=60)
        if code != 0 and not stdout:
            Logger.error(f"扫描手机失败: {err}")
            return {}

        groups = defaultdict(list)
        total_files = 0
        for line in stdout.splitlines():
            path = line.strip()
            if not path:
                continue
            total_files += 1
            fname = path.split("/")[-1]
            m = IMG_TIMESTAMP_PATTERN.search(fname)
            if m:
                groups[m.group(1)].append(path)

        Logger.info(f"全盘扫描到 {total_files} 个文件，匹配到 {len(groups)} 个带有时间戳格式的文件组")

        candidates = {}
        for ts, paths in groups.items():
            if len(paths) > 1 or (len(paths) == 1 and not EXACT_IMG_PATTERN.match(paths[0].split("/")[-1])):
                candidates[ts] = paths

        total_cand_files = sum(len(v) for v in candidates.values())
        msg = f"扫描完毕，发现 {len(candidates)} 个候选对比组 (共 {total_cand_files} 个文件)"
        if progress_cb:
            progress_cb("scanned", len(candidates), total_cand_files, msg)
        Logger.info(msg)
        return candidates

    def pull_and_analyze(
        self,
        candidates: Dict[str, List[str]],
        progress_cb: Optional[Callable[[str, int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """将候选文件拉取至本地缓存，并行提取尺寸分辨率，执行视觉相似度分类打标"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        manifest_groups = []
        total_groups = len(candidates)
        Logger.step("2/3", f"正在拉取对比图片至本机缓存，并进行高精度视觉指纹比对...")

        for idx, (ts, paths) in enumerate(sorted(candidates.items(), reverse=True), start=1):
            group_dir = self.data_dir / ts
            group_dir.mkdir(parents=True, exist_ok=True)

            file_entries = []
            for p_idx, phone_path in enumerate(paths):
                fname = phone_path.split("/")[-1]
                safe_name = f"{p_idx}_{fname}"
                local_path = str(group_dir / safe_name)

                # 按需拉取
                if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                    self.adb.pull(phone_path, local_path)

                size_bytes = os.path.getsize(local_path) if os.path.exists(local_path) else 0
                ext = fname.split(".")[-1].lower() if "." in fname else ""
                w, h = get_image_dimensions(local_path)

                # Web 友好格式转换 (HEIC/INSP/DNG -> JPEG preview)
                preview_file = safe_name
                if ext in ["heic", "insp", "dng"]:
                    jpg_preview = local_path + ".preview.jpg"
                    if not os.path.exists(jpg_preview) or os.path.getsize(jpg_preview) == 0:
                        convert_to_preview_jpg(local_path, jpg_preview)
                    if os.path.exists(jpg_preview):
                        preview_file = os.path.basename(jpg_preview)

                file_entries.append({
                    "id": f"{ts}_{p_idx}",
                    "phone_path": phone_path,
                    "local_path": local_path,
                    "filename": fname,
                    "size_bytes": size_bytes,
                    "size_str": format_size(size_bytes),
                    "ext": ext,
                    "width": w,
                    "height": h,
                    "resolution_str": f"{w} × {h}" if (w and h) else "未知",
                    "preview_url": f"/images/{ts}/{preview_file}",
                    "raw_url": f"/images/{ts}/{safe_name}"
                })

            # 调用智能分类器打标
            classified = ImageClassifier.classify_group(file_entries, self.similarity_threshold)

            manifest_groups.append({
                "timestamp": ts,
                "formatted_date": format_timestamp(ts),
                "badges": classified["badges"],
                "files": classified["files"],
                "file_count": len(classified["files"]),
                "has_different_content": classified["has_different_content"],
                "has_real_duplicate": classified["has_real_duplicate"]
            })

            pct = (idx * 100) // total_groups if total_groups > 0 else 100
            msg = f"正在拉取与比对: 第 {idx}/{total_groups} 组 (IMG_{ts})"
            if progress_cb:
                progress_cb("analyzing", idx, total_groups, msg)
            elif idx % 10 == 0 or idx == total_groups:
                Logger.log(f"进度: {idx}/{total_groups} 组 ({pct}%)")

        # 生成 manifest 统计
        total_files = sum(len(g["files"]) for g in manifest_groups)
        auto_selected = sum(1 for g in manifest_groups for f in g["files"] if f.get("auto_select"))
        auto_bytes = sum(f.get("size_bytes", 0) for g in manifest_groups for f in g["files"] if f.get("auto_select"))
        protected = sum(1 for g in manifest_groups for f in g["files"] if f.get("role") == "independent")

        manifest = {
            "summary": {
                "total_groups": len(manifest_groups),
                "total_files": total_files,
                "auto_selected_files": auto_selected,
                "auto_selected_bytes": auto_bytes,
                "auto_selected_size_str": format_size(auto_bytes),
                "protected_files": protected,
                "scan_time": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "groups": manifest_groups
        }

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        if progress_cb:
            progress_cb("done", total_groups, total_files, f"扫描比对完成！共分析 {total_groups} 组，建议删除 {auto_selected} 张")

        Logger.step("3/3", "索引生成完毕！")
        Logger.success(f"总对比组数: {manifest['summary']['total_groups']}")
        Logger.info(f"🛡️ 识别并保护的独立照片: {protected} 张 (同名不同图，严禁删除)")
        Logger.warn(f"🎯 真正确认是相同图片的缩略图/缓存: {auto_selected} 张")
        Logger.info(f"预计可释放存储: {manifest['summary']['auto_selected_size_str']}")
        return manifest
