import json
import os
import shutil
import subprocess
from typing import Dict, List, Optional


class WxMCPError(Exception):
    pass


class WxMCPKeyError(WxMCPError):
    pass


class WxMCPClient:
    def __init__(self):
        self.exe = self._find()

    def _find(self) -> Optional[str]:
        candidates = [
            os.path.expanduser("~/.local/share/wx-mcp/wx-mcp.exe"),
            os.path.expanduser("~/.local/share/wx-mcp/wx-mcp"),
            "wx-mcp",
            "wx-mcp.exe",
        ]
        install_root = os.path.expanduser("~/.local/share/wx-mcp")
        if os.path.exists(install_root):
            for root, _, files in os.walk(install_root):
                for file in files:
                    if file in {"wx-mcp.exe", "wx-mcp"}:
                        candidates.append(os.path.join(root, file))
        for path in candidates:
            found = shutil.which(path)
            if found:
                return found
            if os.path.exists(path):
                return path
        return None

    def installed(self) -> bool:
        return self.exe is not None

    def ready(self) -> bool:
        if not self.installed():
            return False
        try:
            self._run(["sessions", "--limit", "1"])
            return True
        except WxMCPError:
            return False

    def _run(self, args: List[str]) -> Optional[list]:
        if not self.exe:
            raise WxMCPError("wx-mcp not found")
        result = subprocess.run([self.exe] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if result.returncode != 0:
            err = (result.stderr or "").strip() or (result.stdout or "").strip()
            if "key" in err.lower():
                raise WxMCPKeyError(err)
            raise WxMCPError(err)
        if not result.stdout.strip():
            return []
        return json.loads(result.stdout)

    def contacts(self, limit: int = 200) -> List[Dict]:
        return self._run(["sessions", "--limit", str(limit)]) or []

    def messages(self, session: str, limit: int = 5000) -> List[Dict]:
        return self._run(["history", session, "--limit", str(limit)]) or []
