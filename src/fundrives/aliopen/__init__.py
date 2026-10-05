"""阿里云盘开放平台 SDK。

本包挂在共享命名空间 ``fundrives`` 下（PEP 420 隐式命名空间包）：
``fundrive-alipan`` / ``fundrive-baidu`` / ``fundrive-lanzou`` / ``fundrive-quark``
四个发行包各自往 ``fundrives`` 里放一个子包。因此 ``src/fundrives/`` **不能**有
``__init__.py``（会把隐式命名空间变成常规包，屏蔽兄弟插件），版本号、``py.typed``
和公开符号一律挂在本子包上。
"""

from importlib.metadata import PackageNotFoundError, version

from .auth import AliPanAuth
from .drive import AliOpenManage

try:
    __version__ = version("fundrive-alipan")
except PackageNotFoundError:  # 未安装（例如直接从源码树运行）时的兜底
    __version__ = "0.0.0.dev0"

__all__ = ["AliOpenManage", "AliPanAuth"]
