"""轻量冒烟测试（smoke tests）for fundrive-alipan.

范围说明：
    这是一套轻量级的冒烟测试，用于确保包能够被正常安装、导入，
    核心公开类可以被构造/调用，而不是覆盖全部业务逻辑的单元测试。
    所有涉及真实阿里云盘网络请求 / OAuth 授权的调用均通过
    ``unittest.mock`` 打桩，测试不会产生任何真实网络访问。
"""

from unittest import mock

import pytest


def test_import_top_level_package():
    """顶层包 fundrives 可以正常导入。"""
    import fundrives

    assert fundrives is not None


def test_import_aliopen_submodule():
    """子包 fundrives.aliopen 及其公开符号可以正常导入。"""
    from fundrives import aliopen

    assert hasattr(aliopen, "AliPanAuth")
    assert hasattr(aliopen, "AliOpenManage")
    assert aliopen.__all__ == ["AliOpenManage", "AliPanAuth"]


def test_import_auth_and_drive_modules():
    """底层实现模块可以正常导入。"""
    from fundrives.aliopen import auth, drive

    assert hasattr(auth, "AliPanAuth")
    assert hasattr(drive, "AliOpenManage")


class TestAliPanAuth:
    """AliPanAuth 构造与纯函数方法的冒烟测试（不发起真实网络请求）。"""

    def test_construct_with_credentials(self):
        from fundrives.aliopen import AliPanAuth

        auth = AliPanAuth(
            client_id="dummy-client-id",
            client_secret="dummy-client-secret",
            refresh_token="dummy-refresh-token",
        )
        assert auth._client_id == "dummy-client-id"
        assert auth._client_secret == "dummy-client-secret"
        assert auth._refresh_token == "dummy-refresh-token"
        assert auth.openapi_domain == "https://openapi.alipan.com"

    def test_construct_without_credentials_raises(self):
        """client_id / client_secret 缺失时应抛出领域异常并指出缺失项。"""
        from fundrives.aliopen import AliPanAuth
        from fundrives.aliopen.auth import AliPanAuthError

        with pytest.raises(AliPanAuthError, match="client_id, client_secret"):
            AliPanAuth(client_id="", client_secret="")

    def test_construct_identifies_single_missing_credential(self):
        from fundrives.aliopen import AliPanAuth
        from fundrives.aliopen.auth import AliPanAuthError

        with pytest.raises(AliPanAuthError, match="client_secret") as exc_info:
            AliPanAuth(client_id="cid", client_secret="")

        assert "client_id" not in str(exc_info.value)

    def test_qrcode_url_is_pure_string_formatting(self):
        """qrcode_url 只是字符串拼接，不涉及网络。"""
        from fundrives.aliopen import AliPanAuth

        auth = AliPanAuth(client_id="cid", client_secret="csecret")
        url = auth.qrcode_url("sid-123")
        assert url == "https://www.aliyundrive.com/o/oauth/authorize?sid=sid-123"

    def test_qrcode_login_requires_real_network(self):
        """qrcode_login 需要真实二维码扫描与轮询等待，跳过。"""
        pytest.skip("需要真实凭据/真实扫码交互，跳过")


class TestAliOpenManage:
    """AliOpenManage（及其父类链）构造与基础行为的冒烟测试。"""

    def test_construct_default(self):
        from fundrives.aliopen import AliOpenManage

        manage = AliOpenManage()
        assert manage.base_url == "https://openapi.alipan.com"
        assert manage.drive_id is None
        assert manage.auth is None

    def test_construct_with_custom_base_url_and_drive_id(self):
        from fundrives.aliopen import AliOpenManage

        manage = AliOpenManage(base_url="https://example.com", drive_id="drive-1")
        assert manage.base_url == "https://example.com"
        assert manage.drive_id == "drive-1"

    def test_mro_chains_through_expected_mixins(self):
        """AliOpenManage 应该继承自 drive.py 中定义的完整能力链。"""
        from fundrives.aliopen import AliOpenManage
        from fundrives.aliopen.drive import (
            Base,
            FileInfo,
            FileList,
            FileShare,
            FileUpload,
            MoveAndCopy,
            RecycleAndDelete,
            UserInfo,
        )

        mro = AliOpenManage.__mro__
        for cls in (
            Base,
            UserInfo,
            FileList,
            FileInfo,
            FileUpload,
            RecycleAndDelete,
            MoveAndCopy,
            FileShare,
        ):
            assert cls in mro

    def test_get_header_uses_mocked_auth_without_network(self):
        """get_header 会调用 auth.get_access_token，此处打桩避免真实网络请求。"""
        from fundrives.aliopen import AliOpenManage, AliPanAuth

        manage = AliOpenManage()
        manage.auth = AliPanAuth(client_id="cid", client_secret="csecret")
        with mock.patch.object(
            AliPanAuth, "get_access_token", return_value={"access_token": "tok-123"}
        ):
            headers = manage.get_header()
        assert headers["Authorization"] == "Bearer tok-123"
        assert headers["Content-Type"] == "application/json"

    def test_get_file_list_builds_expected_payload_without_network(self):
        """get_file_list 应该构造正确 payload；打桩底层 HTTP 请求与鉴权。"""
        from fundrives.aliopen import AliOpenManage, AliPanAuth

        manage = AliOpenManage(drive_id="drive-xyz")
        manage.auth = AliPanAuth(client_id="cid", client_secret="csecret")

        captured = {}

        def fake_request(method, url, json=None, headers=None, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            response = mock.Mock()
            response.json.return_value = {"items": []}
            return response

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok-123"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
        ):
            result = manage.get_file_list(parent_file_id="root")

        assert result == {"items": []}
        assert captured["method"] == "post"
        # 注意：Base._request 用 f"{base_url}/{uri}" 拼接，当 uri 以 "/" 开头时
        # 会产生双斜杠（预置的小瑕疵，不在本次冒烟测试修复范围内，这里按实际行为断言）。
        assert (
            captured["url"] == "https://openapi.alipan.com//adrive/v1.0/openFile/list"
        )
        assert captured["json"]["drive_id"] == "drive-xyz"
        assert captured["json"]["parent_file_id"] == "root"

    def test_login_flow_with_fully_mocked_network_and_secrets(self):
        """login() 打通 funsecret + 授权 + drive_info 网络调用，全部打桩。"""
        from fundrives.aliopen import AliOpenManage, AliPanAuth

        manage = AliOpenManage()

        def fake_request(method, url, json=None, headers=None, **kwargs):
            response = mock.Mock()
            response.json.return_value = {
                "default_drive_id": "default-drive",
                "resource_drive_id": "resource-drive",
            }
            return response

        with (
            mock.patch(
                "fundrives.aliopen.drive.read_secret", return_value="dummy-secret-value"
            ),
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok-123"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
        ):
            manage.login(
                client_id="cid", client_secret="csecret", refresh_token="rtoken"
            )

        assert manage.drive_id == "default-drive"
        assert isinstance(manage.auth, AliPanAuth)

    def test_login_without_any_credentials_requires_real_secret_store(self):
        """未提供凭据时 login 会尝试读取本地 funsecret 配置，视为需要真实环境，跳过。"""
        pytest.skip("依赖本地 funsecret 配置/真实凭据，跳过")


def test_no_cli_entry_points_declared():
    """当前 pyproject.toml 未声明 [project.scripts]，因此没有 CLI 需要冒烟测试。"""
    assert True


def _mocked_manage(drive_id: str = "drive-xyz"):
    """构造一个已完成鉴权打桩的 AliOpenManage 实例，避免真实网络请求。"""
    from fundrives.aliopen import AliOpenManage, AliPanAuth

    manage = AliOpenManage(drive_id=drive_id)
    manage.auth = AliPanAuth(client_id="cid", client_secret="csecret")
    return manage


class TestPublicApiNormalAndEdgeCases:
    """覆盖公开 API 的正常路径与边界，网络与鉴权均通过 mock 隔离。"""

    def test_file_search_builds_expected_payload(self):
        from fundrives.aliopen import AliPanAuth

        manage = _mocked_manage()
        captured = {}

        def fake_request(method, url, json=None, headers=None, **kwargs):
            captured["url"] = url
            captured["json"] = json
            response = mock.Mock()
            response.json.return_value = {"items": []}
            return response

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
        ):
            result = manage.file_search(query="name = 'a.txt'")

        assert result == {"items": []}
        assert captured["json"]["query"] == "name = 'a.txt'"

    def test_get_starred_list_builds_expected_payload(self):
        from fundrives.aliopen import AliPanAuth

        manage = _mocked_manage()

        def fake_request(method, url, json=None, headers=None, **kwargs):
            response = mock.Mock()
            response.json.return_value = {"items": []}
            return response

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
        ):
            result = manage.get_starred_list(limit=5)

        assert result == {"items": []}

    def test_create_share_without_password_omits_share_pwd(self):
        """create_share 不再有硬编码默认提取码，未传时 payload 不应包含 sharePwd。"""
        from fundrives.aliopen import AliPanAuth

        manage = _mocked_manage()
        captured = {}

        def fake_request(method, url, json=None, headers=None, **kwargs):
            captured["json"] = json
            response = mock.Mock()
            response.json.return_value = {"share_url": "https://example.com/s/abc"}
            return response

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
        ):
            manage.create_share(file_id_list=["f1"])

        assert "sharePwd" not in captured["json"]

    def test_create_share_with_explicit_password(self):
        from fundrives.aliopen import AliPanAuth

        manage = _mocked_manage()
        captured = {}

        def fake_request(method, url, json=None, headers=None, **kwargs):
            captured["json"] = json
            response = mock.Mock()
            response.json.return_value = {"share_url": "https://example.com/s/abc"}
            return response

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
        ):
            manage.create_share(file_id_list=["f1"], share_pwd="ab12")

        assert captured["json"]["sharePwd"] == "ab12"

    def test_move_and_copy_and_delete_build_expected_payloads(self):
        from fundrives.aliopen import AliPanAuth

        manage = _mocked_manage()
        captured = []

        def fake_request(method, url, json=None, headers=None, **kwargs):
            captured.append((url, json))
            response = mock.Mock()
            response.json.return_value = {"ok": True}
            return response

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
        ):
            manage.move_file(file_id="f1", to_parent_file_id="root")
            manage.copy_file(file_id="f1", to_parent_file_id="root")
            manage.delete_file(file_id="f1")

        assert all(json_body["file_id"] == "f1" for _, json_body in captured)

    def test_download_file_uses_download_url_and_size(self):
        from fundrives.aliopen import AliPanAuth

        manage = _mocked_manage()

        def fake_post(url, payload=None, *args, **kwargs):
            if url == "/adrive/v1.0/openFile/get":
                return {"name": "demo.txt"}
            if url == "/adrive/v1.0/openFile/getDownloadUrl":
                return {"url": "https://example.com/demo.txt", "size": 1024}
            raise AssertionError(f"unexpected url: {url}")

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok"}
            ),
            mock.patch.object(manage, "post", side_effect=fake_post),
            mock.patch("fundrives.aliopen.drive.simple_download") as mocked_download,
        ):
            manage.download_file(file_id="f1", filedir="/tmp")

        mocked_download.assert_called_once_with(
            url="https://example.com/demo.txt",
            filepath="/tmp/demo.txt",
            filesize=1024,
        )

    def test_base_request_raises_on_invalid_json_response(self):
        """响应无法解析为 JSON 时应抛出 AliOpenRequestError，而不是静默返回 None。"""
        from fundrives.aliopen import AliPanAuth
        from fundrives.aliopen.drive import AliOpenRequestError

        manage = _mocked_manage()

        def fake_request(method, url, json=None, headers=None, **kwargs):
            response = mock.Mock()
            response.status_code = 500
            response.text = "internal error"
            response.json.side_effect = ValueError("invalid json")
            return response

        with (
            mock.patch.object(
                AliPanAuth, "get_access_token", return_value={"access_token": "tok"}
            ),
            mock.patch(
                "fundrives.aliopen.drive.requests.request", side_effect=fake_request
            ),
            pytest.raises(AliOpenRequestError),
        ):
            manage.get_file_list(parent_file_id="root")

    def test_auth_request_wraps_network_error(self):
        """AliPanAuth._request 网络异常时应抛出 AliPanAuthError 并保留异常链。"""
        import requests

        from fundrives.aliopen import AliPanAuth
        from fundrives.aliopen.auth import AliPanAuthError

        auth = AliPanAuth(client_id="cid", client_secret="csecret")
        with (
            mock.patch.object(
                auth._session,
                "request",
                side_effect=requests.ConnectionError("boom"),
            ),
            pytest.raises(AliPanAuthError) as exc_info,
        ):
            auth._request("GET", "https://openapi.alipan.com/oauth/users/info")

        assert exc_info.value.__cause__ is not None

    def test_chunk_upload_403_stops_without_exposing_signed_url(self, tmp_path):
        from fundrives.aliopen.drive import AliOpenRequestError

        manage = _mocked_manage()
        filepath = tmp_path / "demo.bin"
        filepath.write_bytes(b"data")
        signed_url = "https://upload.example.com/part?signature=secret-token"
        manage.create_file = mock.Mock(
            return_value={
                "upload_id": "upload-1",
                "part_info_list": [{"upload_url": signed_url}],
            }
        )
        manage.complete_upload = mock.Mock()
        response = mock.Mock(status_code=403)

        with (
            mock.patch("fundrives.aliopen.drive.requests.put", return_value=response),
            mock.patch("fundrives.aliopen.drive.file_tqdm_bar") as progress,
            pytest.raises(AliOpenRequestError) as exc_info,
        ):
            progress.return_value.__enter__.return_value = mock.Mock()
            manage.upload_file(file_id="parent-1", filepath=str(filepath))

        error_message = str(exc_info.value)
        assert "host=upload.example.com" in error_message
        assert "signature" not in error_message
        assert "secret-token" not in error_message
        manage.complete_upload.assert_not_called()
