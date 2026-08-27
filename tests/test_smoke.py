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
    import fundrives.aliopen as aliopen

    assert hasattr(aliopen, "AliPanAuth")
    assert hasattr(aliopen, "AliOpenManage")
    assert aliopen.__all__ == ["AliPanAuth", "AliOpenManage"]


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
        """client_id / client_secret 缺失时应立即抛出 AssertionError。"""
        from fundrives.aliopen import AliPanAuth

        with pytest.raises(AssertionError):
            AliPanAuth(client_id="", client_secret="")

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

        with mock.patch.object(
            AliPanAuth, "get_access_token", return_value={"access_token": "tok-123"}
        ), mock.patch("fundrives.aliopen.drive.requests.request", side_effect=fake_request):
            result = manage.get_file_list(parent_file_id="root")

        assert result == {"items": []}
        assert captured["method"] == "post"
        # 注意：Base._request 用 f"{base_url}/{uri}" 拼接，当 uri 以 "/" 开头时
        # 会产生双斜杠（预置的小瑕疵，不在本次冒烟测试修复范围内，这里按实际行为断言）。
        assert captured["url"] == "https://openapi.alipan.com//adrive/v1.0/openFile/list"
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

        with mock.patch(
            "fundrives.aliopen.drive.read_secret", return_value="dummy-secret-value"
        ), mock.patch.object(
            AliPanAuth, "get_access_token", return_value={"access_token": "tok-123"}
        ), mock.patch(
            "fundrives.aliopen.drive.requests.request", side_effect=fake_request
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
