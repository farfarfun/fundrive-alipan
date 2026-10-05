import os
from typing import Any
from urllib.parse import urlsplit

import requests
from farlog import getLogger
from funfile import file_tqdm_bar
from funget import simple_download, single_upload
from funsecret import read_secret

from .auth import AliPanAuth

logger = getLogger("fundrive")


class AliOpenRequestError(Exception):
    """阿里云盘开放平台接口调用相关异常，携带请求方法、URL 与响应上下文。"""


# 默认请求超时（连接秒数, 读取秒数）。不设超时时服务端不响应会让整个进程挂死。
DEFAULT_TIMEOUT: tuple[int, int] = (10, 60)

# 异常信息里最多携带多少字符的响应正文，避免把超长正文整段塞进日志
_MAX_BODY_IN_ERROR = 500


def _brief(text: str | None, limit: int = _MAX_BODY_IN_ERROR) -> str:
    """截断过长的响应正文，供异常信息使用。

    :param text: 原始响应正文
    :param limit: 保留的最大字符数
    :return: 截断后的文本
    """
    text = "" if text is None else str(text)
    return text if len(text) <= limit else f"{text[:limit]}...(truncated)"


class Base:
    """阿里云盘开放平台请求基类，封装鉴权、通用请求方法。"""

    def __init__(
        self,
        base_url: str | None = None,
        drive_id: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """初始化请求基类。

        :param base_url: 开放平台接口根地址，默认 ``https://openapi.alipan.com``
        :param drive_id: 网盘 drive_id，登录成功后会自动填充
        """
        self.base_url = base_url or "https://openapi.alipan.com"
        self.auth: AliPanAuth | None = None
        self.drive_id = drive_id

    def get_header(self) -> dict[str, str]:
        """构造带 access_token 的公共请求头。

        :return: 包含 ``Content-Type``、``Authorization`` 的请求头字典
        """
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth.get_access_token()['access_token']}",
        }

    def _request(
        self,
        method: str,
        uri: str,
        payload: dict[str, Any] | None = None,
        *args: Any,
        timeout: tuple[int, int] | int | None = None,
        **kwargs: Any,
    ) -> Any:
        """发起底层 HTTP 请求并解析 JSON 响应。

        :param method: HTTP 方法，如 ``get``/``post``
        :param uri: 相对路径或完整 URL（以 ``https://`` 开头时视为完整 URL）
        :param payload: JSON 请求体
        :param timeout: 请求超时，默认 :data:`DEFAULT_TIMEOUT`
        :return: 响应体解析出的 JSON 数据
        :raises AliOpenRequestError: 网络请求失败、HTTP 状态码非 2xx、或响应无法
            解析为 JSON；异常信息统一带上请求方法、URL、HTTP 状态码与（截断后的）
            响应正文，并通过 ``raise ... from err`` 保留原始异常链
        """
        method = method.lower()

        if uri.startswith("https://"):
            url = uri
        else:
            url = f"{self.base_url}/{uri}"

        try:
            response = requests.request(
                method,
                url,
                json=payload,
                headers=self.get_header(),
                timeout=timeout or DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            # 连接失败、超时、DNS 错误等：原始异常只有一个裸 URL，没有业务上下文
            raise AliOpenRequestError(
                f"request failed: method={method}, url={url}: {type(e).__name__}: {e}"
            ) from e

        if response.status_code >= 400:
            # 开放平台在 4xx/5xx 时同样会返回 JSON 错误体，照原样返回会让调用方
            # 把失败当成功（拿不到字段再抛 KeyError），必须在这里显式失败。
            raise AliOpenRequestError(
                f"request failed: method={method}, url={url}, "
                f"status_code={response.status_code}, response={_brief(response.text)}"
            )

        try:
            return response.json()
        except ValueError as e:
            raise AliOpenRequestError(
                f"invalid JSON response: method={method}, url={url}, "
                f"status_code={response.status_code}, "
                f"response={_brief(response.text)}"
            ) from e

    def post(
        self, uri: str, payload: dict[str, Any] | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        """发起 POST 请求。

        :param uri: 相对路径或完整 URL
        :param payload: JSON 请求体
        :return: 响应体解析出的 JSON 数据
        """
        return self._request("post", uri, payload, *args, **kwargs)

    def get(self, uri: str, *args: Any, **kwargs: Any) -> Any:
        """发起 GET 请求。

        :param uri: 相对路径或完整 URL
        :return: 响应体解析出的 JSON 数据
        """
        return self._request("get", uri, *args, **kwargs)


class UserInfo(Base):
    """用户与 drive 信息接口。

    参考：https://www.yuque.com/aliyundrive/zpfszx/mbb50w
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def login(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        use_resource: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """登录阿里云盘，初始化鉴权信息并填充 ``drive_id``。

        :param client_id: 阿里云盘开放平台应用 client_id，缺省时从 ``funsecret`` 读取
        :param client_secret: 阿里云盘开放平台应用 client_secret，缺省时从
            ``funsecret`` 读取
        :param refresh_token: 刷新令牌，如未提供则从 ``funsecret`` 配置读取
        :param use_resource: 为 ``True`` 时使用 ``resource_drive_id``，否则使用
            ``default_drive_id``
        :return: 无返回值，登录成功后 ``self.auth``、``self.drive_id`` 会被填充
        """
        refresh_token = refresh_token or read_secret(
            "fundrive", "drives", "alipan", "refresh_token"
        )
        client_id = client_id or read_secret(
            "fundrive", "drives", "alipan", "client_id"
        )
        client_secret = client_secret or read_secret(
            "fundrive", "drives", "alipan", "client_secret"
        )
        self.auth = AliPanAuth(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
        drive_info = self.drive_info()
        self.drive_id = drive_info["default_drive_id"]
        if use_resource:
            self.drive_id = drive_info["resource_drive_id"]

    def user_info(self) -> Any:
        """获取当前用户信息。"""
        return self.get("/oauth/users/info", payload={})

    def vip_info(self) -> Any:
        """获取当前用户的会员信息。"""
        return self.get("/business/v1.0/user/getVipInfo", payload={})

    def drive_info(self) -> Any:
        """获取当前用户的 drive 信息（包含 ``default_drive_id``、``resource_drive_id``）。"""
        return self.post("/adrive/v1.0/user/getDriveInfo", payload={})


class FileList(UserInfo):
    """文件列表、搜索相关接口。

    参考：https://www.yuque.com/aliyundrive/zpfszx/zqkqp6
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def get_file_list(
        self,
        parent_file_id: str,
        limit: int = 100,
        marker: str | None = None,
        order_by: str = "name",
        type: str = "all",
    ) -> Any:
        """获取指定目录下的文件列表。

        :param parent_file_id: 父目录 file_id
        :param limit: 单页返回数量
        :param marker: 分页游标，首次请求可不传
        :param order_by: 排序字段
        :param type: 文件类型过滤，可选 ``all``/``file``/``folder``
        :return: 文件列表响应 JSON
        """
        payload = {
            "drive_id": self.drive_id,
            "parent_file_id": parent_file_id,
            "limit": limit,
            "marker": marker,
            "order_by": order_by,
            "type": type,
        }
        return self.post("/adrive/v1.0/openFile/list", payload=payload)

    def file_search(
        self,
        query: str,
        limit: int = 10,
        marker: str | None = None,
        order_by: str = "name",
    ) -> Any:
        """按条件搜索文件。

        :param query: 搜索条件表达式
        :param limit: 单页返回数量
        :param marker: 分页游标
        :param order_by: 排序字段
        :return: 搜索结果响应 JSON
        """
        params = {
            "drive_id": self.drive_id,
            "query": query,
            "limit": limit,
            "marker": marker,
            "order_by": order_by,
        }
        return self.post("/adrive/v1.0/openFile/search", payload=params)

    def get_starred_list(
        self, limit: int = 10, marker: str | None = None, order_by: str = "name"
    ) -> Any:
        """获取已收藏（标星）文件列表。

        :param limit: 单页返回数量
        :param marker: 分页游标
        :param order_by: 排序字段
        :return: 收藏列表响应 JSON
        """
        params = {
            "drive_id": self.drive_id,
            "limit": limit,
            "marker": marker,
            "order_by": order_by,
        }
        return self.post("/openFile/starredList", payload=params)


class FileInfo(FileList):
    """文件详情、下载相关接口。

    参考：https://www.yuque.com/aliyundrive/zpfszx/gogo34oi2gy98w5d
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def get_file_details(
        self,
        file_id: str,
        video_thumbnail_time: int | None = None,
        video_thumbnail_width: int | None = None,
        image_thumbnail_width: int | None = None,
        fields: str | None = None,
    ) -> Any:
        """获取文件详情。

        :param file_id: 文件 file_id
        :param video_thumbnail_time: 视频缩略图截取时间点（ms）
        :param video_thumbnail_width: 视频缩略图宽度
        :param image_thumbnail_width: 图片缩略图宽度
        :param fields: 需要返回的自定义字段
        :return: 文件详情响应 JSON
        """
        url = "/adrive/v1.0/openFile/get"
        body: dict[str, Any] = {"drive_id": self.drive_id, "file_id": file_id}
        if video_thumbnail_time is not None:
            body["video_thumbnail_time"] = video_thumbnail_time
        if video_thumbnail_width is not None:
            body["video_thumbnail_width"] = video_thumbnail_width
        if image_thumbnail_width is not None:
            body["image_thumbnail_width"] = image_thumbnail_width
        if fields is not None:
            body["fields"] = fields
        return self.post(url, payload=body)

    def get_file_by_path(self, file_path: str) -> Any:
        """根据文件路径查找文件。

        :param file_path: 网盘内文件路径
        :return: 文件详情响应 JSON
        """
        url = "/adrive/v1.0/openFile/get_by_path"
        body = {"drive_id": self.drive_id, "file_path": file_path}
        return self.post(url, payload=body)

    def batch_get_file_details(self, file_list: list[dict[str, Any]]) -> Any:
        """批量获取文件详情。

        :param file_list: 文件标识列表，元素形如 ``{"drive_id": ..., "file_id": ...}``
        :return: 批量详情响应 JSON
        """
        url = "/adrive/v1.0/openFile/batch/get"
        body = {"file_list": file_list}
        return self.post(url, payload=body)

    def get_file_download_url(self, file_id: str, expire_sec: int | None = None) -> Any:
        """获取文件下载直链。

        :param file_id: 文件 file_id
        :param expire_sec: 下载链接有效期（秒）
        :return: 包含下载 ``url``、``size`` 等字段的响应 JSON
        """
        url = "/adrive/v1.0/openFile/getDownloadUrl"
        body: dict[str, Any] = {"drive_id": self.drive_id, "file_id": file_id}
        if expire_sec is not None:
            body["expire_sec"] = expire_sec
        return self.post(url, payload=body)

    def download_file(
        self, file_id: str, filedir: str = "./", filepath: str | None = None
    ) -> None:
        """下载文件到本地。

        :param file_id: 文件 file_id
        :param filedir: 保存目录，``filepath`` 未指定时使用该目录 + 原始文件名
        :param filepath: 保存的完整文件路径，优先级高于 ``filedir``
        :return: 无返回值
        :raises AliOpenRequestError: 获取文件信息或下载链接失败
        """
        file_info = self.get_file_details(file_id=file_id)
        file_url = self.get_file_download_url(file_id=file_id)
        simple_download(
            url=file_url["url"],
            filepath=filepath or f"{filedir}/{file_info['name']}",
            filesize=file_url["size"],
        )


class FileUpload(FileInfo):
    """文件上传相关接口。

    参考：https://www.yuque.com/aliyundrive/zpfszx/ezlzok
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def create_file(
        self,
        parent_file_id: str,
        name: str,
        type: str = "file",
        check_name_mode: str = "refuse",
        size: int | None = None,
    ) -> Any:
        """创建文件或文件夹（用于后续分片上传）。

        :param parent_file_id: 父目录 file_id
        :param name: 文件/文件夹名
        :param type: ``file`` 或 ``folder``
        :param check_name_mode: 同名处理策略：
            ``auto_rename`` 自动重命名（存在并发问题）、
            ``refuse`` 同名不创建、``ignore`` 同名文件可创建
        :param size: 文件大小（字节），创建文件夹时可不传
        :return: 创建结果响应 JSON，包含 ``file_id``、``upload_id``、
            ``part_info_list`` 等字段
        """
        url = "/adrive/v1.0/openFile/create"
        data = {
            "drive_id": self.drive_id,
            "parent_file_id": parent_file_id,
            "name": name,
            "type": type,
            "check_name_mode": check_name_mode,
            "size": size,
        }
        return self.post(url, payload=data)

    def get_upload_url(self, file_id: str, upload_id: str) -> Any:
        """获取分片上传地址。

        :param file_id: 文件 file_id
        :param upload_id: 上传任务 upload_id
        :return: 包含 ``part_info_list`` 的响应 JSON
        :raises AliOpenRequestError: 请求失败或响应不是合法 JSON

        .. note::
            历史实现是 ``requests.post(url, params=data)``，``url`` 是相对路径
            ``/adrive/v1.0/openFile/getUploadUrl``，``requests`` 会直接抛
            ``MissingSchema: Invalid URL ... No scheme supplied``，而且既没带
            ``Authorization`` 头也没带 JSON body，这个方法此前 100% 不可用。
        """
        url = "/adrive/v1.0/openFile/getUploadUrl"
        data = {"drive_id": self.drive_id, "file_id": file_id, "upload_id": upload_id}
        return self.post(url, payload=data)

    def list_uploaded_parts(self, file_id: str, upload_id: str) -> Any:
        """列出已上传的分片。

        :param file_id: 文件 file_id
        :param upload_id: 上传任务 upload_id
        :return: 已上传分片列表响应 JSON
        """
        url = "/adrive/v1.0/openFile/listUploadedParts"
        data = {"drive_id": self.drive_id, "file_id": file_id, "upload_id": upload_id}
        return self.post(url, payload=data)

    def complete_upload(self, file_id: str, upload_id: str) -> Any:
        """完成分片上传，通知服务端合并文件。

        :param file_id: 文件 file_id
        :param upload_id: 上传任务 upload_id
        :return: 完成结果响应 JSON
        """
        url = "/adrive/v1.0/openFile/complete"
        data = {"drive_id": self.drive_id, "file_id": file_id, "upload_id": upload_id}
        return self.post(url, payload=data)

    def upload_file2(self, file_id: str, filepath: str) -> None:
        """单分片上传本地文件（适用于较小文件）。

        :param file_id: 目标目录 file_id
        :param filepath: 本地文件路径
        :return: 无返回值
        """
        filesize = os.path.getsize(filepath)
        info = self.create_file(file_id, os.path.basename(filepath), size=filesize)

        headers = self.get_header()
        headers.update(
            {
                "Content-Length": str(filesize),
                "Content-Type": "application/octet-stream",
            }
        )
        # 这里必须用上面补过 Content-Length / Content-Type 的 headers；
        # 历史实现又调了一次 get_header()，上面那几行等于白写。
        single_upload(
            url=info["part_info_list"][0]["upload_url"],
            filepath=filepath,
            headers=headers,
        )
        self.complete_upload(file_id=info["file_id"], upload_id=info["upload_id"])

    def upload_file(
        self, file_id: str, filepath: str, chunk_size: int = 512 * 1024
    ) -> None:
        """分片上传本地文件，并带进度条显示。

        :param file_id: 目标目录 file_id
        :param filepath: 本地文件路径
        :param chunk_size: 每个分片大小（字节）
        :return: 无返回值
        :raises AliOpenRequestError: 创建文件失败，或某个分片上传返回非 2xx
        """
        filesize = os.path.getsize(filepath)
        part_info = self.create_file(file_id, os.path.basename(filepath), size=filesize)
        # create_file 返回的是**新文件**的 file_id，后面 complete_upload 必须用它；
        # 传入的 file_id 是父目录，用父目录 id 去 complete 必然失败。
        new_file_id = part_info["file_id"]
        with (
            open(filepath, "rb") as f,
            file_tqdm_bar(
                path=filepath,
                total=filesize,
            ) as progress_bar,
        ):
            for i in range(len(part_info["part_info_list"])):
                part_info_item = part_info["part_info_list"][i]
                data = f.read(chunk_size)
                upload_host = urlsplit(part_info_item["upload_url"]).hostname
                try:
                    resp = requests.put(
                        data=data,
                        url=part_info_item["upload_url"],
                        timeout=DEFAULT_TIMEOUT,
                    )
                except requests.RequestException as e:
                    raise AliOpenRequestError(
                        f"upload part failed: part={i + 1}/"
                        f"{len(part_info['part_info_list'])}, host={upload_host}, "
                        f"file_id={new_file_id}, upload_id={part_info['upload_id']}, "
                        f"filepath={filepath}: {type(e).__name__}: {e}"
                    ) from e
                # 原实现只拦 403，4xx/5xx 的其它失败会被当成上传成功，
                # 最后 complete 出来一个内容残缺的文件。
                if resp.status_code >= 400:
                    raise AliOpenRequestError(
                        f"upload part rejected: status_code={resp.status_code}, "
                        f"part={i + 1}/{len(part_info['part_info_list'])}, "
                        f"host={upload_host}, file_id={new_file_id}, "
                        f"upload_id={part_info['upload_id']}, filepath={filepath}, "
                        f"response={_brief(resp.text)}"
                    )
                progress_bar.update(len(data))
        self.complete_upload(file_id=new_file_id, upload_id=part_info["upload_id"])


class RecycleAndDelete(FileUpload):
    """回收站与删除相关接口。

    参考：https://www.yuque.com/aliyundrive/zpfszx/get3mkr677pf10ws
    """

    def put_file_in_recycle_bin(self, file_id: str) -> Any:
        """将文件放入回收站。

        :param file_id: 文件 file_id
        :return: 操作结果响应 JSON
        """
        uri = "/adrive/v1.0/openFile/recyclebin/trash"
        payload = {"drive_id": self.drive_id, "file_id": file_id}
        return self.post(uri, payload=payload)

    def delete_file(self, file_id: str) -> Any:
        """彻底删除文件（不经过回收站）。

        :param file_id: 文件 file_id
        :return: 操作结果响应 JSON
        """
        url = "/adrive/v1.0/openFile/delete"
        payload = {"drive_id": self.drive_id, "file_id": file_id}
        return self.post(url, payload=payload)

    def get_async_task_status(self, async_task_id: str) -> Any:
        """获取异步任务（如删除、复制）状态。

        :param async_task_id: 异步任务 id
        :return: 任务状态响应 JSON
        """
        url = "/adrive/v1.0/openFile/async_task/get"
        payload = {"async_task_id": async_task_id}
        return self.post(url, payload=payload)


class MoveAndCopy(RecycleAndDelete):
    """文件移动、复制相关接口。

    参考：https://www.yuque.com/aliyundrive/zpfszx/gzeh9ecpxihziqrc
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def move_file(
        self,
        file_id: str,
        to_parent_file_id: str,
        check_name_mode: str = "refuse",
        new_name: str | bool = False,
    ) -> Any:
        """移动文件到指定目录。

        :param file_id: 文件 file_id
        :param to_parent_file_id: 目标父目录 file_id，根目录为 ``root``
        :param check_name_mode: 同名文件处理模式：
            ``ignore`` 允许同名文件；
            ``auto_rename`` 云端存在同名文件时自动重命名；
            ``refuse`` 云端存在同名文件时拒绝创建新文件（默认）
        :param new_name: 云端存在同名文件时使用的新名字
        :return: 操作结果响应 JSON
        """
        url = "/adrive/v1.0/openFile/move"
        payload = {
            "drive_id": self.drive_id,
            "file_id": file_id,
            "to_parent_file_id": to_parent_file_id,
            "check_name_mode": check_name_mode,
            "new_name": new_name,
        }
        return self.post(url, payload=payload)

    def copy_file(
        self,
        file_id: str,
        to_parent_file_id: str,
        to_drive_id: str | None = None,
        auto_rename: bool = False,
    ) -> Any:
        """复制文件到指定目录。

        :param file_id: 文件 file_id
        :param to_parent_file_id: 目标父目录 file_id，根目录为 ``root``
        :param to_drive_id: 目标 drive，默认是当前 ``drive_id``
        :param auto_rename: 目标文件夹下存在同名文件时是否自动重命名，默认
            ``False``（允许同名文件）
        :return: 操作结果响应 JSON
        """
        url = "/adrive/v1.0/openFile/copy"
        payload = {
            "drive_id": self.drive_id,
            "file_id": file_id,
            "to_drive_id": to_drive_id,
            "to_parent_file_id": to_parent_file_id,
            "auto_rename": auto_rename,
        }
        return self.post(url, payload=payload)


class FileShare(MoveAndCopy):
    """文件分享相关接口。

    参考：https://www.yuque.com/aliyundrive/zpfszx/lylz73ifo1epqz70
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def create_share(
        self,
        file_id_list: list[str],
        expiration: int = -1,
        share_pwd: str | None = None,
    ) -> Any:
        """创建分享链接。

        :param file_id_list: 文件 id 列表，元素数量范围 [1, 100]
        :param expiration: 分享过期时间，``-1`` 表示永不过期
        :param share_pwd: 分享提取码，需由调用方显式传入（如需固定提取码，建议
            通过 ``funsecret`` 或环境变量注入），不传则不设置提取码
        :return: 创建结果响应 JSON，包含分享链接等信息
        """
        url = "/adrive/v1.0/openFile/createShare"
        payload: dict[str, Any] = {
            "driveId": self.drive_id,
            "fileIdList": file_id_list,
            "expiration": expiration,
        }
        if share_pwd is not None:
            payload["sharePwd"] = share_pwd
        return self.post(url, payload=payload)


class AliOpenManage(FileShare):
    """阿里云盘开放平台管理入口，聚合用户信息、文件增删改查与分享等能力。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
