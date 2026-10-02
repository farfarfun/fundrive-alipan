import time
from io import StringIO
from typing import Any

import requests
from farcache import ttl_cache
from farlog import getLogger
from qrcode.main import QRCode

logger = getLogger("fundrive")
aliyundrive_com = "https://www.aliyundrive.com"


class AliPanAuthError(Exception):
    """阿里云盘 OAuth 鉴权相关异常，携带请求方法与 URL 等定位上下文。"""


class AliPanAuth:
    """阿里云盘开放平台 OAuth 鉴权客户端。

    负责二维码登录、access_token 获取与刷新等鉴权流程。
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str | None = None,
    ) -> None:
        """初始化鉴权客户端。

        :param client_id: 阿里云盘开放平台应用 client_id
        :param client_secret: 阿里云盘开放平台应用 client_secret
        :param refresh_token: 刷新令牌，如未提供则需要通过 :meth:`qrcode_login` 获取
        """
        self.openapi_domain = "https://openapi.alipan.com"
        missing_credentials = [
            name
            for name, value in (
                ("client_id", client_id),
                ("client_secret", client_secret),
            )
            if not value
        ]
        if missing_credentials:
            raise AliPanAuthError(
                f"missing required credentials: {', '.join(missing_credentials)}"
            )

        self._session = requests.Session()
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        data: str | bytes | dict[str, str] | Any = None,
        json: Any = None,
        files: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """发起底层 HTTP 请求。

        :param method: HTTP 方法，如 ``get``/``post``
        :param url: 请求地址
        :param params: URL 查询参数
        :param headers: 请求头，缺省时使用内置的浏览器 UA
        :param data: 表单/原始请求体
        :param json: JSON 请求体
        :param files: 文件上传内容
        :return: ``requests.Response`` 对象
        :raises AliPanAuthError: 请求发送失败（网络错误、超时等），异常信息包含
            请求方法与 URL，并通过 ``raise ... from err`` 保留原始异常链
        """
        if not headers:
            pcs_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            pcs_headers = {
                "Origin": aliyundrive_com,
                "Referer": aliyundrive_com + "/",
                "User-Agent": pcs_ua,
            }

            headers = dict(pcs_headers)

        try:
            resp = self._session.request(
                method,
                url,
                params=params,
                headers=headers,
                data=data,
                json=json,
                files=files,
                **kwargs,
            )
            return resp
        except requests.RequestException as err:
            raise AliPanAuthError(
                f"AliOpenAuth._request failed: method={method}, url={url}"
            ) from err

    def qrcode_url(self, sid: str) -> str:
        """根据登录会话 id 生成二维码扫码跳转地址。

        :param sid: 登录会话 id
        :return: 扫码跳转 URL
        """
        return f"{aliyundrive_com}/o/oauth/authorize?sid={sid}"

    def get_qrcode_info(self) -> dict[str, Any]:
        """获取扫码登录所需的二维码信息。

        :return: 包含 ``sid`` 等字段的响应 JSON
        :raises AliPanAuthError: 请求失败
        """
        data: dict[str, Any] = {
            "scopes": [
                "user:base",
                "file:all:read",
                "file:all:write",
            ],
            "width": None,
            "height": None,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        url = f"{self.openapi_domain}/oauth/authorize/qrcode"
        return self._request("POST", url, json=data).json()

    def scan_status(self, sid: str) -> dict[str, Any]:
        """查询扫码登录状态。

        :param sid: 登录会话 id
        :return: 包含 ``status``、``authCode`` 等字段的响应 JSON
        :raises AliPanAuthError: 请求失败
        """
        url = f"{self.openapi_domain}/oauth/qrcode/{sid}/status"
        return self._request("Get", url).json()

    @ttl_cache(ttl=3600)
    def get_access_token(
        self,
        auth_code: str | None = None,
        refresh_token: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """获取或刷新 access_token。

        :param auth_code: 授权码，扫码登录成功后获得
        :param refresh_token: 刷新令牌，优先级低于 ``auth_code``，缺省时使用
            构造函数传入的 ``refresh_token``
        :return: 包含 ``access_token`` 等字段的响应 JSON
        :raises AliPanAuthError: 请求失败
        """
        data = {
            "grant_type": "authorization_code" if auth_code else "refresh_token",
            "code": auth_code,
            "refresh_token": refresh_token or self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if data["code"] is None and data["refresh_token"] is None:
            logger.error("No authorization code provided")
            return self.qrcode_login()

        url = f"{self.openapi_domain}/oauth/access_token"
        resp = self._request("post", url, json=data)
        return resp.json()

    def qrcode_login(self) -> dict[str, str]:
        """通过终端打印二维码，等待用户扫码完成登录。

        :return: :meth:`get_access_token` 返回的 access_token 信息
        :raises AliPanAuthError: 底层请求失败
        :raises RuntimeError: 在超时时间内未完成扫码登录
        """
        info = self.get_qrcode_info()
        sid = info["sid"]
        qr = QRCode()
        qr.add_data(self.qrcode_url(sid))
        qr.make(fit=True)
        f = StringIO()
        qr.print_ascii(out=f, tty=False, invert=True)
        f.seek(0)
        logger.info(f.read())
        logger.info("  [red b]Please scan the qrcode to login in 120 seconds[/red b]")
        interval = 2 * 60  # wait 2min
        sleep = 2

        auth_code = ""
        for _ in range(interval // sleep):
            time.sleep(2)

            info = self.scan_status(sid)
            if info["status"] == "LoginSuccess":
                auth_code = info["authCode"]
                break

        if not auth_code:
            raise RuntimeError(f"Login failed: qrcode scan timed out for sid={sid}")
        return self.get_access_token(auth_code)
