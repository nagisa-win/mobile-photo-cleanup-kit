import sys
import argparse
import webbrowser
from pathlib import Path

from phone_cleaner.config import DEFAULT_PORT, DEFAULT_HOST, DEFAULT_DATA_DIR, DEFAULT_SIMILARITY_THRESHOLD
from phone_cleaner.core.adb import ADBClient
from phone_cleaner.core.scanner import PhoneScanner
from phone_cleaner.server.app import start_cleaner_server
from phone_cleaner.utils.logger import Logger

def cmd_status(args):
    """查看 ADB 状态与已连接设备"""
    Logger.banner("ADB 手机连接状态检测")
    client = ADBClient(adb_bin=args.adb)
    devices = client.list_devices()
    if not devices:
        Logger.warn("未检测到已连接的 Android 设备。请确认：")
        print("  1. 手机已开启【开发者选项】与【USB 调试】")
        print("  2. USB 连接模式设为【传输文件(MTP)】")
        print("  3. 手机屏幕上已点击【允许此电脑进行 USB 调试】")
        sys.exit(1)

    Logger.success(f"检测到 {len(devices)} 台设备连接:")
    for d in devices:
        status_color = Logger.GREEN if d["status"] == "device" else Logger.YELLOW
        print(f"  • 设备序列号: {Logger.BOLD}{d['serial']}{Logger.RESET} (状态: {status_color}{d['status']}{Logger.RESET})")

def cmd_scan(args):
    """扫描手机并生成视觉去重对比索引"""
    Logger.banner("扫描手机相册与缩略图分析")
    adb = ADBClient(adb_bin=args.adb, serial=args.serial)
    if not adb.ensure_connected():
        Logger.error("未检测到在线的 Android 设备，请连接手机后再试。")
        sys.exit(1)

    scanner = PhoneScanner(
        adb_client=adb,
        data_dir=Path(args.data_dir),
        similarity_threshold=args.threshold
    )
    candidates = scanner.scan_candidate_groups()
    if not candidates:
        Logger.info("手机内置存储中未发现重复或缩略图对比组。")
        return

    scanner.pull_and_analyze(candidates)

def cmd_serve(args):
    """启动本地 Web 对比与清理服务"""
    data_dir = Path(args.data_dir)
    manifest = data_dir / "manifest.json"
    if not manifest.exists():
        Logger.warn(f"未找到索引文件 {manifest}，建议先执行 'cleaner scan' 或使用 'cleaner run'。")

    url = f"http://localhost:{args.port}"
    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    start_cleaner_server(port=args.port, host=args.host, data_dir=data_dir, manifest_path=manifest)

def cmd_run(args):
    """一键完整流水线：连接检测 -> 扫描分析 -> 启动 Web 服务 -> 打开浏览器"""
    Logger.banner("手机相册缩略图与重复文件清理 Kit - 一键启动")
    adb = ADBClient(adb_bin=args.adb, serial=args.serial)
    if not adb.ensure_connected():
        Logger.error("未检测到在线的 Android 设备，请连接手机后再试。")
        sys.exit(1)

    scanner = PhoneScanner(
        adb_client=adb,
        data_dir=Path(args.data_dir),
        similarity_threshold=args.threshold
    )

    manifest_path = Path(args.data_dir) / "manifest.json"
    if not args.skip_scan or not manifest_path.exists():
        candidates = scanner.scan_candidate_groups()
        if candidates:
            scanner.pull_and_analyze(candidates)

    url = f"http://localhost:{args.port}"
    Logger.info(f"即将打开清理对比界面: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    start_cleaner_server(port=args.port, host=args.host, data_dir=Path(args.data_dir), manifest_path=manifest_path)

def main():
    parser = argparse.ArgumentParser(
        prog="cleaner",
        description="📱 手机相册缩略图与重复图片对比清理工程化工具包 (Mobile Photo Cleanup Kit)"
    )
    parser.add_argument("--adb", help="指定 adb 二进制绝对路径")
    parser.add_argument("-s", "--serial", help="指定目标设备序列号")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="本地临时拉取与索引目录")

    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    # status
    p_status = subparsers.add_parser("status", help="检测 ADB 连接状态与设备信息")
    p_status.set_defaults(func=cmd_status)

    # scan
    p_scan = subparsers.add_parser("scan", help="仅扫描手机相册并进行视觉比对分析")
    p_scan.add_argument("--threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD, help="视觉相似度阈值 (默认 0.88)")
    p_scan.set_defaults(func=cmd_scan)

    # serve
    p_serve = subparsers.add_parser("serve", help="仅启动 Web 交互对比与清理服务")
    p_serve.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="Web 服务监听端口 (默认 8899)")
    p_serve.add_argument("--host", default=DEFAULT_HOST, help="Web 监听主机地址")
    p_serve.add_argument("--open", action="store_true", default=True, help="启动后自动打开系统浏览器")
    p_serve.set_defaults(func=cmd_serve)

    # run
    p_run = subparsers.add_parser("run", help="一键执行全流程 (检测 -> 扫描 -> 启动 Web -> 开启浏览器)")
    p_run.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="Web 服务监听端口 (默认 8899)")
    p_run.add_argument("--host", default=DEFAULT_HOST, help="Web 监听主机地址")
    p_run.add_argument("--threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD, help="视觉相似度阈值 (默认 0.88)")
    p_run.add_argument("--skip-scan", action="store_true", help="若本地已有索引，跳过重新扫描")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not args.command:
        # 默认执行 run 命令
        cmd_run(args)
    else:
        args.func(args)

if __name__ == "__main__":
    main()
