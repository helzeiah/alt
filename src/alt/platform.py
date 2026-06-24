import sys
from enum import Enum


class Platform(Enum):
    MACOS = "macos"
    LINUX = "linux"
    WSL = "wsl"
    UNKNOWN = "unknown"

    @classmethod
    def detect(cls) -> "Platform":
        if sys.platform == "darwin":
            return cls.MACOS
        if sys.platform.startswith("linux"):
            try:
                if "microsoft" in open("/proc/version").read().lower():
                    return cls.WSL
            except OSError:
                pass
            return cls.LINUX
        return cls.UNKNOWN


CURRENT = Platform.detect()
