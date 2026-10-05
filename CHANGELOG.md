# CHANGELOG

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，变更记录按版本倒序排列。

## [未发布]

### 修复

- `pyproject.toml` 补齐 `requests` 直接依赖（此前仅通过 `funget` 的传递依赖提供，未显式声明）
- `AliPanAuth.__init__` 校验 `client_id`/`client_secret` 不再使用 `assert`（优化模式下可能被移除），改为显式判断并抛出 `AliPanAuthError`，错误信息指出具体缺失的字段
- 分片上传遇到 403 时不再记录带签名的完整 `upload_url`（可能泄露可用凭据），改为只记录脱敏后的主机名，并抛出 `AliOpenRequestError` 终止上传，不再静默继续
- 删除 `src/fundrives/__init__.py`：`fundrives` 是 `fundrive-alipan` / `fundrive-baidu` /
  `fundrive-lanzou` / `fundrive-quark` 共用的 PEP 420 隐式命名空间，加上 `__init__.py`
  会把它变成常规包并屏蔽兄弟插件包，同时让四个 wheel 争抢同一个文件。该文件曾在
  `e5ffc66` 删除过，被 `a21ddbd` 重新加了回来，本次再次删除并在子包文档里写明原因。
  版本号改由 `fundrives.aliopen.__version__` 提供。
- `py.typed` 从共享命名空间目录 `src/fundrives/` 移到真实包根 `src/fundrives/aliopen/`，
  符合 PEP 561 对命名空间包的要求（放在共享目录里同样会造成多包文件冲突）。
- `FileUpload.get_upload_url` 此前是 `requests.post("/adrive/v1.0/openFile/getUploadUrl", params=...)`，
  传的是相对路径、没有 `Authorization` 头也没有 JSON body，调用必抛
  `requests.exceptions.MissingSchema`，该方法此前 100% 不可用；改为走 `self.post()`。
- `FileUpload.upload_file` 的 `complete_upload` 误用**父目录**的 `file_id`，应当用
  `create_file` 返回的新文件 `file_id`，否则分片上传最后一步必然失败。
- `FileUpload.upload_file2` 构造了带 `Content-Length` / `Content-Type` 的请求头，
  却又调一次 `get_header()` 传给 `single_upload`，补的头全部丢失。
- `FileUpload.upload_file` 的分片上传原先只拦 403，其它 4xx/5xx 被当成上传成功，
  最终 complete 出一个内容残缺的文件；现在非 2xx 一律抛 `AliOpenRequestError`，
  并带上分片序号、脱敏主机名、`file_id`、`upload_id` 与本地路径。

### 变更

- `Base._request` 统一错误处理（SPEC §8.2）：捕获 `requests.RequestException` 转成
  带请求方法与 URL 的 `AliOpenRequestError`（保留异常链）；HTTP 状态码非 2xx 时显式
  失败，不再把开放平台返回的 JSON 错误体当成功数据返回；响应正文在异常信息里截断。
- `Base._request` 与 `AliPanAuth._request` 增加默认超时 `(10, 60)`，服务端不响应时
  不再无限挂起；`AliPanAuth._request` 的非 2xx 也显式失败，但**不回显响应正文**，
  避免把凭据写进日志。
- `uv.lock` 按组织规范不纳入版本管理（见 PR #1 `chore: 不再跟踪 uv.lock`），
  `.gitignore` 已忽略。下面 `[1.3.15]` 条目里的「提交 `uv.lock` 保证可复现构建」
  只反映当时的状态，当前仓库不再提交锁文件。
- `.gitignore` 去掉 `a21ddbd` 引入的重复忽略段（`.run/`、`logs/`、`*.db`、`*.rar` 等重复了两遍）。

## [1.3.15] - 2026-09-03

### 修复

- 日志迁移到组织自有包 `farlog`，函数缓存迁移到 `farcache`，移除对 `funutil` 的直接依赖
- `AliPanAuth._request` 不再吞掉原始异常，改为抛出 `AliPanAuthError` 并保留异常链与请求上下文
- `Base._request` JSON 解析失败时改为抛出 `AliOpenRequestError`（携带请求方法、URL、状态码、响应内容），不再静默返回 `None`
- `create_share` 移除硬编码的默认分享提取码 `"6666"`，改为按需由调用方显式传入
- 公开 API 类型标注统一改为 Python 3.10 原生泛型/联合类型写法（`str | None`、`list[str]`、`dict[...]`），移除 `typing.Optional/List/Dict/Union`
- 补充公开类与方法的中文 docstring，明确用途、参数、返回值与异常行为

### 新增

- 补充 `CHANGELOG.md`
- 提交 `uv.lock` 保证可复现构建
- 为公开 API 增加更多基于 mock 的正常路径测试（搜索、分享、移动、复制、删除、下载、上传）

### 变更

- README 补充项目简介、安装命令、最小可运行示例与凭据配置说明，并追加组织介绍区块
- `.gitignore` 补充 `*.db`、`*.rar`、`.run/`、`logs/`、`.idea/`、`.vscode/` 忽略规则

## [1.3.14] 及更早版本

早期版本未系统记录变更，详见 Git 提交历史。
