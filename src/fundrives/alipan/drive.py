import os
from typing import List, Optional

import requests
from fundrives.alipan import AliPanAuth
from funfile import file_tqdm_bar
from funget import simple_download, single_upload
from funsecret import read_secret
from funutil import getLogger

logger = getLogger("fundrive")


class Base:
    def __init__(self, base_url=None, drive_id=None, *args, **kwargs):
        self.base_url = base_url or "https://openapi.alipan.com"
        self.auth: AliPanAuth = None
        self.drive_id = drive_id

    def get_header(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth.get_access_token()['access_token']}",
        }

    def _request(self, method, uri, payload, *args, **kwargs):
        method = method.lower()

        if uri.startswith("https://"):
            url = uri
        else:
            url = f"{self.base_url}/{uri}"
        response = requests.request(
            method, url, json=payload, headers=self.get_header()
        )
        try:
            return response.json()
        except Exception as e:
            logger.error(
                f"error: {e},with code:{response.status_code}, response: {response.text}"
            )

    def post(self, uri, payload, *args, **kwargs):
        return self._request("post", uri, payload, *args, **kwargs)

    def get(self, uri, *args, **kwargs):
        return self._request("get", uri, *args, **kwargs)


class UserInfo(Base):
    """
    https://www.yuque.com/aliyundrive/zpfszx/mbb50w
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def login(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        use_resource=False,
        *args,
        **kwargs,
    ):
        """
        登录阿里云盘
        :param client_id:
        :param client_secret:
        :param refresh_token: 刷新令牌，如未提供则从配置文件读取

        :return: 登录是否成功
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

    def user_info(self):
        return self.get("/oauth/users/info", payload={})

    def vip_info(self):
        return self.get("/business/v1.0/user/getVipInfo", payload={})

    def drive_info(self):
        return self.post("/adrive/v1.0/user/getDriveInfo", payload={})


class FileList(UserInfo):
    """
    https://www.yuque.com/aliyundrive/zpfszx/zqkqp6
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_file_list(self, parent_file_id, limit=100, marker=None, order_by="name"):
        payload = {
            "drive_id": self.drive_id,
            "parent_file_id": parent_file_id,
            "limit": limit,
            "marker": marker,
            "order_by": order_by,
        }
        return self.post("/adrive/v1.0/openFile/list", payload=payload)

    def file_search(self, query, limit=10, marker=None, order_by="name"):
        params = {
            "drive_id": self.drive_id,
            "query": query,
            "limit": limit,
            "marker": marker,
            "order_by": order_by,
        }
        return self.post("/adrive/v1.0/openFile/search", payload=params)

    def get_starred_list(self, limit=10, marker=None, order_by="name"):
        params = {
            "drive_id": self.drive_id,
            "limit": limit,
            "marker": marker,
            "order_by": order_by,
        }
        return self.post("/openFile/starredList", payload=params)


class FileInfo(FileList):
    """
    https://www.yuque.com/aliyundrive/zpfszx/gogo34oi2gy98w5d
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # 定义获取文件详情的函数
    def get_file_details(
        self,
        file_id,
        video_thumbnail_time=None,
        video_thumbnail_width=None,
        image_thumbnail_width=None,
        fields=None,
    ):
        url = "/adrive/v1.0/openFile/get"
        body = {"drive_id": self.drive_id, "file_id": file_id}
        if video_thumbnail_time is not None:
            body["video_thumbnail_time"] = video_thumbnail_time
        if video_thumbnail_width is not None:
            body["video_thumbnail_width"] = video_thumbnail_width
        if image_thumbnail_width is not None:
            body["image_thumbnail_width"] = image_thumbnail_width
        if fields is not None:
            body["fields"] = fields
        return self.post(url, payload=body)

    # 定义根据文件路径查找文件的函数
    def get_file_by_path(self, file_path):
        url = "/adrive/v1.0/openFile/get_by_path"
        body = {"drive_id": self.drive_id, "file_path": file_path}
        return self.post(url, payload=body)

    # 定义批量获取文件详情的函数
    def batch_get_file_details(self, file_list):
        url = "/adrive/v1.0/openFile/batch/get"
        body = {"file_list": file_list}
        return self.post(url, payload=body)

    # 定义获取文件下载链接的函数
    def get_file_download_url(self, file_id, expire_sec=None):
        url = "/adrive/v1.0/openFile/getDownloadUrl"
        body = {"drive_id": self.drive_id, "file_id": file_id}
        if expire_sec is not None:
            body["expire_sec"] = expire_sec
        return self.post(url, payload=body)

    def download_file(self, file_id, filepath="./"):
        file_info = self.get_file_details(file_id=file_id)
        file_url = self.get_file_download_url(file_id=file_id)
        simple_download(
            url=file_url["url"],
            filepath=f"{filepath}/{file_info['name']}",
            filesize=file_url["size"],
        )


class FileUpload(FileInfo):
    """
    https://www.yuque.com/aliyundrive/zpfszx/ezlzok
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def create_file(
        self, parent_file_id, name, type="file", check_name_mode="refuse", size=None
    ):
        """
        :param parent_file_id:
        :param name:
        :param type:file | folder
        :param check_name_mode:
                auto_rename 自动重命名，存在并发问题
                refuse 同名不创建
                ignore 同名文件可创建
        :return:
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

    def get_upload_url(self, file_id, upload_id):
        url = "/adrive/v1.0/openFile/getUploadUrl"
        data = {"drive_id": self.drive_id, "file_id": file_id, "upload_id": upload_id}
        return requests.post(url, params=data)

    def list_uploaded_parts(self, file_id, upload_id):
        url = "/adrive/v1.0/openFile/listUploadedParts"
        data = {"drive_id": self.drive_id, "file_id": file_id, "upload_id": upload_id}
        return self.post(url, payload=data)

    def complete_upload(self, file_id, upload_id):
        url = "/adrive/v1.0/openFile/complete"
        data = {"drive_id": self.drive_id, "file_id": file_id, "upload_id": upload_id}
        return self.post(url, payload=data)

    def upload_file2(self, file_id, filepath):
        filesize = os.path.getsize(filepath)
        info = self.create_file(file_id, os.path.basename(filepath), size=filesize)

        headers = self.get_header()
        headers.update(
            {
                "Content-Length": str(filesize),
                "Content-Type": "application/octet-stream",
            }
        )
        single_upload(
            url=info["part_info_list"][0]["upload_url"],
            filepath=filepath,
            headers=self.get_header(),
        )
        self.complete_upload(file_id=info["file_id"], upload_id=info["upload_id"])

    def upload_file(self, file_id, filepath, chunk_size=512 * 1024):
        filesize = os.path.getsize(filepath)
        part_info = self.create_file(file_id, os.path.basename(filepath), size=filesize)
        """上传数据"""
        with open(filepath, "rb") as f:
            with file_tqdm_bar(
                path=filepath,
                total=filesize,
            ) as progress_bar:
                for i in range(len(part_info["part_info_list"])):
                    part_info_item = part_info["part_info_list"][i]
                    data = f.read(chunk_size)
                    resp = requests.put(data=data, url=part_info_item["upload_url"])
                    if resp.status_code == 403:
                        logger.error(
                            f"upload_url({part_info_item['upload_url']}) expired"
                        )
                    progress_bar.update(len(data))
        self.complete_upload(file_id=file_id, upload_id=part_info["upload_id"])


class RecycleAndDelete(FileUpload):
    """
    https://www.yuque.com/aliyundrive/zpfszx/get3mkr677pf10ws
    """

    def put_file_in_recycle_bin(self, file_id):
        """
        将文件放入回收站
        """
        uri = "/adrive/v1.0/openFile/recyclebin/trash"
        payload = {"drive_id": self.drive_id, "file_id": file_id}
        return self.post(uri, payload=payload)

    def delete_file(self, file_id):
        """
        删除文件
        """
        url = "/adrive/v1.0/openFile/delete"
        payload = {"drive_id": self.drive_id, "file_id": file_id}
        return self.post(url, payload=payload)

    def get_async_task_status(self, async_task_id):
        """
        获取异步任务状态
        """
        url = "/adrive/v1.0/openFile/async_task/get"
        payload = {"async_task_id": async_task_id}
        return self.post(url, payload=payload)


class MoveAndCopy(RecycleAndDelete):
    """
    https://www.yuque.com/aliyundrive/zpfszx/gzeh9ecpxihziqrc
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def move_file(
        self, file_id, to_parent_file_id, check_name_mode="refuse", new_name=False
    ):
        """
        :param file_id: file_id
        :param to_parent_file_id: 父文件ID、根目录为 root
        :param check_name_mode: 同名文件处理模式，可选值如下：
                    ignore：允许同名文件；
                    auto_rename：当发现同名文件是，云端自动重命名。
                    refuse：当云端存在同名文件时，拒绝创建新文件。
                    默认为 refuse
        :param new_name: 当云端存在同名文件时，使用的新名字
        :return:
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
        self, file_id, to_parent_file_id, to_drive_id=None, auto_rename=False
    ):
        """

        :param file_id: file_id
        :param to_parent_file_id:  str	父文件ID、根目录为 root
        :param to_drive_id: str	    目标drive，默认是当前drive_id
        :param auto_rename: bool	当目标文件夹下存在同名文件时，是否自动重命名，默认为 false，默认允许同名文件
        :return:
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
    """
    https://www.yuque.com/aliyundrive/zpfszx/lylz73ifo1epqz70
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def create_share(self, file_id_list: List[str], expiration=-1, share_pwd="6666"):
        """
        :param file_id_list: 文件ID数据，元数数量 [1, 100]
        :param expiration: 分享过期时间
        :param share_pwd: 分享提取码
        :return:
        """
        url = "/adrive/v1.0/openFile/createShare"
        payload = {
            "driveId": self.drive_id,
            "fileIdList": file_id_list,
            "expiration": expiration,
            "sharePwd": share_pwd,
        }
        return self.post(url, payload=payload)


class AlipanManage(FileShare):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
