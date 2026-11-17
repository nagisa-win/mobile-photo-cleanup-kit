import os
import json
import threading
import urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Optional, Dict, Any

from phone_cleaner.config import DEFAULT_PORT, DEFAULT_HOST, DEFAULT_DATA_DIR, DEFAULT_MANIFEST_PATH, DEFAULT_SIMILARITY_THRESHOLD
from phone_cleaner.core.adb import ADBClient
from phone_cleaner.core.scanner import PhoneScanner
from phone_cleaner.utils.logger import Logger
from phone_cleaner.utils.helpers import format_size, is_safe_phone_path

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".svg": "image/svg+xml"
}

# 全局扫描任务状态管理器
class ScanManager:
    lock = threading.Lock()
    is_scanning = False
    step = "idle"
    step_text = "空闲就绪"
    current = 0
    total = 0
    progress = 0
    message = ""
    error = None
    summary = None

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        with cls.lock:
            return {
                "is_scanning": cls.is_scanning,
                "step": cls.step,
                "step_text": cls.step_text,
                "current": cls.current,
                "total": cls.total,
                "progress": cls.progress,
                "message": cls.message,
                "error": cls.error,
                "summary": cls.summary
            }

    @classmethod
    def start_scan(cls, adb_client: ADBClient, data_dir: Path, threshold: float = DEFAULT_SIMILARITY_THRESHOLD, clean_cache: bool = False):
        with cls.lock:
            if cls.is_scanning:
                return False, "扫描任务已在运行中"
            cls.is_scanning = True
            cls.step = "starting"
            cls.step_text = "准备启动扫描..."
            cls.current = 0
            cls.total = 0
            cls.progress = 5
            cls.message = "正在连接手机 ADB..."
            cls.error = None
            cls.summary = None

        def run_thread():
            try:
                scanner = PhoneScanner(adb_client=adb_client, data_dir=data_dir, similarity_threshold=threshold)
                if clean_cache:
                    scanner.clean_cache()

                def progress_cb(step_name, current, total, msg):
                    with cls.lock:
                        cls.step = step_name
                        cls.current = current
                        cls.total = total
                        cls.message = msg
                        if step_name == "scanning":
                            cls.step_text = "正在扫描手机内置存储文件..."
                            cls.progress = 15
                        elif step_name == "scanned":
                            cls.step_text = f"发现 {current} 组对比文件"
                            cls.progress = 25
                        elif step_name == "analyzing":
                            cls.step_text = f"正在拉取与比对图片 ({current}/{total})"
                            if total > 0:
                                cls.progress = 25 + int((current / total) * 70)
                        elif step_name == "done":
                            cls.step_text = "扫描比对完成！"
                            cls.progress = 100

                candidates = scanner.scan_candidate_groups(progress_cb=progress_cb)
                if not candidates:
                    with cls.lock:
                        cls.is_scanning = False
                        cls.step = "done"
                        cls.step_text = "未发现重复或缩略图"
                        cls.progress = 100
                        cls.message = "手机相册中没有发现重复文件或缩略图。"
                    return

                manifest = scanner.pull_and_analyze(candidates, progress_cb=progress_cb)
                with cls.lock:
                    cls.is_scanning = False
                    cls.step = "done"
                    cls.progress = 100
                    cls.summary = manifest.get("summary")
                    cls.message = f"扫描完毕！找到 {len(manifest.get('groups', []))} 组对比图片。"
            except Exception as e:
                Logger.error(f"扫描任务发生异常: {e}")
                with cls.lock:
                    cls.is_scanning = False
                    cls.step = "error"
                    cls.error = str(e)
                    cls.step_text = "扫描过程出错"
                    cls.message = str(e)

        t = threading.Thread(target=run_thread, daemon=True)
        t.start()
        return True, "扫描任务已启动"


class CleanerRequestHandler(SimpleHTTPRequestHandler):
    adb_client = ADBClient()
    data_dir = Path(DEFAULT_DATA_DIR)
    manifest_path = Path(DEFAULT_MANIFEST_PATH)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html"]:
            self.serve_file(INDEX_FILE, "text/html; charset=utf-8")
        elif path == "/api/data":
            self.handle_api_data()
        elif path == "/api/adb_status" or path == "/api/devices":
            self.handle_adb_status()
        elif path == "/api/scan_status":
            self.send_json(ScanManager.get_status())
        elif path.startswith("/images/"):
            sub_path = urllib.parse.unquote(path[len("/images/"):])
            file_path = self.data_dir / sub_path
            if file_path.exists():
                ext = file_path.suffix.lower()
                mime = MIME_TYPES.get(ext, "application/octet-stream")
                self.serve_file(file_path, mime)
            else:
                self.send_error(404, f"Image not found: {sub_path}")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/delete":
            self.handle_api_delete()
        elif path in ["/api/scan", "/api/rescan"]:
            self.handle_api_scan()
        else:
            self.send_error(404, "Not Found")

    def serve_file(self, full_path: Path, content_type: str):
        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def handle_api_data(self):
        if not self.manifest_path.exists():
            self.send_json({"error": "Manifest not found. Please scan first.", "summary": {}, "groups": []}, status=200)
            return
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.send_json(data)
        except Exception as e:
            self.send_json({"error": str(e), "summary": {}, "groups": []}, status=500)

    def handle_adb_status(self):
        try:
            devices = self.adb_client.list_devices()
            online = [d for d in devices if d["status"] == "device"]
            self.send_json({
                "connected": len(online) > 0,
                "current_device": self.adb_client.serial or (online[0]["serial"] if online else None),
                "devices": devices
            })
        except Exception as e:
            self.send_json({"connected": False, "devices": [], "error": str(e)}, status=500)

    def handle_api_scan(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        threshold = float(body.get("threshold", DEFAULT_SIMILARITY_THRESHOLD))
        clean_cache = bool(body.get("clean_cache", False))
        serial = body.get("serial")
        if serial:
            self.adb_client.serial = serial

        if not self.adb_client.ensure_connected():
            self.send_json({"success": False, "error": "未检测到已连接的 Android 手机，请连接并在手机端开启 USB 调试。"}, status=400)
            return

        success, msg = ScanManager.start_scan(
            adb_client=self.adb_client,
            data_dir=self.data_dir,
            threshold=threshold,
            clean_cache=clean_cache
        )
        self.send_json({"success": success, "message": msg})

    def handle_api_delete(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        try:
            body = json.loads(post_data.decode("utf-8"))
            phone_paths = body.get("phone_paths", [])

            if not phone_paths:
                self.send_json({"error": "No phone paths provided"}, status=400)
                return

            Logger.info(f"收到 API 删除请求，准备删除 {len(phone_paths)} 个手机文件...")
            deleted = []
            failed = []
            freed_bytes = 0

            for p in phone_paths:
                if not is_safe_phone_path(p):
                    failed.append({"path": p, "reason": "安全检查拦截：非安全存储目录路径"})
                    continue

                f_size = self.adb_client.get_file_size(p)
                success, msg = self.adb_client.remove_file(p, verify=True)
                if success:
                    deleted.append({"path": p, "size_bytes": f_size})
                    freed_bytes += f_size
                    Logger.success(f"已删除手机端文件: {p}")
                else:
                    failed.append({"path": p, "reason": msg})
                    Logger.error(f"删除失败: {p} ({msg})")

            # 同步更新 manifest
            if self.manifest_path.exists():
                try:
                    with open(self.manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    deleted_set = {d["path"] for d in deleted}
                    for g in manifest.get("groups", []):
                        for f in g.get("files", []):
                            if f["phone_path"] in deleted_set:
                                f["deleted"] = True

                    with open(self.manifest_path, "w", encoding="utf-8") as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    Logger.error(f"更新 manifest 失败: {e}")

            self.send_json({
                "success": len(failed) == 0,
                "deleted_count": len(deleted),
                "failed_count": len(failed),
                "freed_bytes": freed_bytes,
                "freed_size_str": format_size(freed_bytes),
                "deleted": deleted,
                "failed": failed
            })
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def start_cleaner_server(
    port: int = DEFAULT_PORT,
    host: str = DEFAULT_HOST,
    data_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None
):
    """启动本地 Web 服务器"""
    if data_dir:
        CleanerRequestHandler.data_dir = Path(data_dir)
    if manifest_path:
        CleanerRequestHandler.manifest_path = Path(manifest_path)

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, CleanerRequestHandler)
    Logger.banner("📱 手机相册对比清理 Kit - Web 服务已启动")
    Logger.success(f"访问地址: http://localhost:{port}")
    Logger.info("按 Ctrl+C 可停止服务\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        Logger.info("\n服务正在关闭...")
        httpd.server_close()
        Logger.success("服务已安全退出。")
