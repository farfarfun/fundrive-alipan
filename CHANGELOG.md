# CHANGELOG

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，变更记录按版本倒序排列。

## [未发布]

### 修复

- `pyproject.toml` 补齐 `requests` 直接依赖（此前仅通过 `funget` 的传递依赖提供，未显式声明）
- `AliPanAuth.__init__` 校验 `client_id`/`client_secret` 不再使用 `assert`（优化模式下可能被移除），改为显式判断并抛出 `AliPanAuthError`，错误信息指出具体缺失的字段
- 分片上传遇到 403 时不再记录带签名的完整 `upload_url`（可能泄露可用凭据），改为只记录脱敏后的主机名，并抛出 `AliOpenRequestError` 终止上传，不再静默继续

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
