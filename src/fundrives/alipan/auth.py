import time
from io import StringIO
from typing import Optional, Dict, Union, Any

import requests
from funutil import getLogger
from funutil.cache import ttl_cache
from qrcode.main import QRCode

logger = getLogger("fundrive")
aliyundrive_com = "https://www.aliyundrive.com"


class AliPanAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str = None,
    ):
        self.openapi_domain = "https://openapi.aliyundrive.com"
        assert client_id and client_secret, "client_id and client_secret must be set"

        self._session = requests.Session()
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Union[str, bytes, Dict[str, str], Any] = None,
        json: Any = None,
        files: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> requests.Response:
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
        except Exception as err:
            raise Exception("AliOpenAuth._request")

    def qrcode_url(self, sid: str) -> str:
        return f"{aliyundrive_com}/o/oauth/authorize?sid={sid}"

    def get_qrcode_info(self):
        data: Dict[str, Any] = dict(
            scopes=[
                "user:base",
                "file:all:read",
                "file:all:write",
            ],
            width=None,
            height=None,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        url = f"{self.openapi_domain}/oauth/authorize/qrcode"
        return self._request("POST", url, json=data).json()

    def scan_status(self, sid: str):
        url = f"{self.openapi_domain}/oauth/qrcode/{sid}/status"
        return self._request("Get", url).json()

    @ttl_cache(ttl=3600)
    def get_access_token(
        self, auth_code: str = None, refresh_token=None, *args, **kwargs
    ) -> Dict[str, Any]:
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

    def qrcode_login(
        self,
    ) -> Dict[str, str]:
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
            raise Exception("Login failed")
        return self.get_access_token(auth_code)
