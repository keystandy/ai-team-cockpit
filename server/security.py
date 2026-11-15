from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .config import Settings


SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ark-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
)


def redact(text: str) -> str:
    value = text
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CredentialBroker:
    def __init__(self, settings: Settings):
        self.settings = settings

    def deepseek_env(self) -> dict[str, str]:
        value = os.environ.get("DEEPSEEK_API_KEY", "")
        if not value:
            try:
                raw = self.settings.dsh_credentials.read_text(
                    encoding="utf-8", errors="ignore"
                )
                match = re.search(r"sk-[A-Za-z0-9_-]{20,}", raw)
                if match:
                    value = match.group(0)
            except OSError:
                pass
        env = {
            "DSH_HOME": str(self.settings.dsh_home),
            "ELECTRON_RUN_AS_NODE": "1",
            "TEMP": str(self.settings.runtime_dir / "tmp"),
            "TMP": str(self.settings.runtime_dir / "tmp"),
        }
        if value:
            env["DEEPSEEK_API_KEY"] = value
        return env


def child_env(settings: Settings, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "TEMP": str(settings.runtime_dir / "tmp"),
            "TMP": str(settings.runtime_dir / "tmp"),
            "PYTHONPYCACHEPREFIX": str(settings.runtime_dir / "python-cache"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "NO_PROXY": "localhost,127.0.0.1,::1",
            "no_proxy": "localhost,127.0.0.1,::1",
            "NO_COLOR": "1",
            "TERM": "dumb",
        }
    )
    if extra:
        env.update(extra)
    return env

