import subprocess
from typing import List, Dict, Optional, Tuple
from phone_cleaner.config import find_adb_binary
from phone_cleaner.utils.logger import Logger
from phone_cleaner.utils.helpers import is_safe_phone_path

class ADBClient:
    """封装 ADB 命令行交互，提供连接检测、安全 Shell 执行、文件拉取与删除校验"""

    def __init__(self, adb_bin: Optional[str] = None, serial: Optional[str] = None):
        self.adb_bin = adb_bin or find_adb_binary()
        self.serial = serial

    def _base_cmd(self) -> List[str]:
        cmd = [self.adb_bin]
        if self.serial:
            cmd.extend(["-s", self.serial])
        return cmd

    def list_devices(self) -> List[Dict[str, str]]:
        """获取所有已连接的 ADB 设备列表"""
        try:
            res = subprocess.run([self.adb_bin, "devices"], stdout=subprocess.PIPE, text=True, timeout=5)
            devices = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("*") or line.startswith("List of devices"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    devices.append({"serial": parts[0], "status": parts[1]})
            return devices
        except Exception as e:
            Logger.error(f"执行 adb devices 失败: {e}")
            return []

    def ensure_connected(self) -> bool:
        """确保至少有一台设备在线"""
        devices = self.list_devices()
        online = [d for d in devices if d["status"] == "device"]
        if not online:
            return False
        if not self.serial:
            self.serial = online[0]["serial"]
        return True

    def shell(self, cmd_str: str, timeout: int = 15) -> Tuple[int, str, str]:
        """在手机端执行 shell 命令"""
        cmd = self._base_cmd() + ["shell", cmd_str]
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    def pull(self, remote_path: str, local_path: str, timeout: int = 30) -> bool:
        """从手机拉取单个文件到本机"""
        cmd = self._base_cmd() + ["pull", remote_path, local_path]
        try:
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
            return p.returncode == 0
        except Exception:
            return False

    def get_file_size(self, remote_path: str) -> int:
        """查询手机端文件实际字节数"""
        code, out, _ = self.shell(f"stat -c '%s' '{remote_path}' 2>/dev/null", timeout=5)
        out = out.strip()
        if out.isdigit():
            return int(out)
        return 0

    def remove_file(self, remote_path: str, verify: bool = True, dry_run: bool = False) -> Tuple[bool, str]:
        """
        在手机端安全删除文件
        包含强制前置白名单校验、rm 指令与后置删除确认
        """
        if not is_safe_phone_path(remote_path):
            return False, "安全检查拒绝：路径不在允许删除的安全白名单内"

        if dry_run:
            Logger.info(f"[Dry-Run] 模拟删除手机文件: {remote_path}")
            return True, "模拟删除成功"

        # 执行 rm -f
        code, _, err = self.shell(f"rm -f '{remote_path}'", timeout=8)
        if code != 0:
            return False, f"rm 命令退出异常 (code {code}): {err}"

        # 校验文件是否确实已不存在
        if verify:
            c_code, c_out, _ = self.shell(f"[ ! -f '{remote_path}' ] && echo 'OK'", timeout=5)
            if "OK" not in c_out:
                return False, "删除校验失败：文件在手机端依然存在"

        return True, "删除成功"
