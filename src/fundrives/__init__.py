"""阿里云盘开放平台 SDK。"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fundrive-alipan")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

from .aliopen import AliOpenManage, AliPanAuth

__all__ = ["AliOpenManage", "AliPanAuth", "__version__"]
