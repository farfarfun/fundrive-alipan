# fundrive-alipan

阿里云盘（AliOpenDrive）开放平台 Python SDK，封装扫码登录、文件列表/搜索、上传下载、
移动复制、回收站与分享链接等常用能力，供 [fundrive](https://github.com/farfarfun/fundrive)
及其他项目以统一接口接入阿里云盘。

## 安装

```bash
pip install fundrive-alipan
# 或
uv add fundrive-alipan
```

## 快速开始

先在阿里云盘开放平台创建应用，获取 `client_id`、`client_secret`，随后扫码登录并列出
根目录文件：

```python
from fundrives.aliopen import AliOpenManage

manage = AliOpenManage()
# client_id / client_secret / refresh_token 未提供时，会尝试从 funsecret 配置读取；
# refresh_token 缺失时会走终端二维码扫码登录流程。
manage.login(client_id="your-client-id", client_secret="your-client-secret")

# 列出网盘根目录文件
result = manage.get_file_list(parent_file_id="root")
for item in result.get("items", []):
    print(item["name"], item["file_id"])
```

## 主要能力

- 二维码扫码登录、access_token 获取与刷新
- 文件列表、搜索、收藏列表
- 文件详情、按路径查找、下载
- 分片上传（带进度条）
- 移动、复制、放入回收站、删除
- 创建分享链接

## 凭据配置

不建议在代码中硬编码 `client_id`/`client_secret`/`refresh_token`，推荐通过
[`funsecret`](https://github.com/farfarfun/funsecret) 配置：

```python
from funsecret import write_secret

write_secret("your-client-id", "fundrive", "drives", "alipan", "client_id")
write_secret("your-client-secret", "fundrive", "drives", "alipan", "client_secret")
write_secret("your-refresh-token", "fundrive", "drives", "alipan", "refresh_token")
```

配置完成后 `manage.login()` 可以不传任何参数。

---

## 关于 farfarfun

[farfarfun](https://github.com/farfarfun) 是一个专注于实用工具库的开源组织，
涵盖云存储、数据处理、AI、多媒体与开发工具链等方向。

- 🏠 组织主页：<https://github.com/farfarfun>
- 📦 PyPI：<https://pypi.org/user/niuliangtao/>
- 📧 联系：farfarfun@qq.com

本项目基于 [MIT](LICENSE) 协议开源。
