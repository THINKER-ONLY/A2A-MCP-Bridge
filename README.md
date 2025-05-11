# A2A-to-MCP Translator (Adapter) - 转换器项目

[![许可证: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
<!-- 如果您有其他徽章，例如构建状态、测试覆盖率等，请在此处添加 -->

## 项目概述

A2A-to-MCP Translator (Adapter) 是一个基于 Python 的网关服务，充当**代理间协议 (A2A)** 与遵循**模型上下文协议 (MCP)** 的服务之间的桥梁。其主要目标是使 A2A 客户端能够通过将 A2A 任务转换为 MCP JSON-RPC 请求，并将 MCP 响应转换回 A2A 任务结果，从而与基于 MCP 的服务进行无缝交互。

该转换器允许通过 A2A 协议进行通信的 AI 代理利用各种支持 MCP 的工具和平台的功能，而无需直接实现 MCP 客户端逻辑。

## 主要特性

*   **A2A 服务器端点**: 实现了一个符合 A2A 规范的服务器端点 (`/`)，用于接收任务。
*   **Agent Card**: 提供了一个 A2A Agent Card (`/.well-known/agent.json`)，详细说明了转换器的能力和技能。
*   **MCP 请求转换**: 解析 A2A `DataPart` 输入，以提取 MCP 调用的参数（目标 URL、方法、参数）。
*   **MCP 通信**: 向指定的目标 MCP 服务发送 JSON-RPC 请求。
*   **响应适配**: 将 MCP 响应（成功或错误）格式化回 A2A `TaskStatus` 和 `Artifacts`。
*   **可配置**: 服务主机、端口和日志级别可以通过环境变量进行配置。
*   **异步处理**: 使用 `asyncio` 和 `httpx` 构建，以实现非阻塞 I/O。

## 先决条件

*   Python 3.9+ (请指定您的项目确切支持的版本范围，例如 `>=3.9, <3.12`)
*   Poetry (推荐，用于依赖管理和运行脚本) 或 pip。

## 安装步骤

1.  **克隆代码仓库:**
    ```bash
    git clone https://github.com/<您的GitHub用户名>/<仓库名称>.git
    cd Adapter
    ```

2.  **创建并激活虚拟环境 (推荐):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Windows 系统请使用 `source .venv\Scripts\activate`
    ```

3.  **安装依赖:**
    *   如果使用 Poetry:
        ```bash
        poetry install
        ```
    *   或者，如果您导出了 `requirements.txt` (例如通过 `poetry export -f requirements.txt --output requirements.txt --without-hashes`):
        ```bash
        pip install -r requirements.txt
        ```

## 配置服务

该服务可以通过环境变量进行配置。您可以直接在 shell 中设置这些变量，或者在项目根目录下创建一个 `.env` 文件 (该文件会被自动加载)。

| 环境变量名           | 描述                                     | 默认值    |
| ---------------------- | ---------------------------------------- | --------- |
| `MCP_GATEWAY_HOST`     | Agent 服务监听的主机地址。                 | `0.0.0.0` |
| `MCP_GATEWAY_PORT`     | Agent 服务监听的端口号。                   | `8080`    |
| `LOG_LEVEL`            | 日志级别 (例如 INFO, DEBUG, ERROR)。     | `INFO`    |
| `PYTHONASYNCIODEBUG`   | 设置为 `1` 以启用 asyncio 的调试模式。     | (未设置)  |

**`.env` 文件示例:**
    ```env
MCP_GATEWAY_HOST=127.0.0.1
MCP_GATEWAY_PORT=8081
LOG_LEVEL=DEBUG
```

## 运行服务

安装完依赖并设置好配置后，您可以运行该服务。

*   **使用 Poetry (如果 `pyproject.toml` 中配置了运行脚本, 例如 `start`):**
    ```bash
    poetry run start
    ```
    (您需要在 `pyproject.toml` 的 `[tool.poetry.scripts]` 部分添加类似 `start = "python -m src.translator"` 的脚本)

*   **直接使用 Python:**
    从项目根目录 (`Adapter/`) 运行:
    ```bash
    python -m src.translator --host <您的主机地址> --port <您的端口号>
    ```
    或者，使用默认配置或 `.env` 文件中的设置:
    ```bash
    python -m src.translator
    ```
    命令行参数 `--host` 和 `--port` 会覆盖环境变量中的设置。

## 与 Agent 交互

### Agent Card

Agent Card 提供了关于此 Agent 的元数据。可以通过以下地址访问：
`http://<配置的主机地址>:<配置的端口号>/.well-known/agent.json`

例如，如果使用默认设置在本地运行： `http://0.0.0.0:8080/.well-known/agent.json`

### 发送任务

任务以 A2A 协议消息的形式发送到根端点：
`http://<配置的主机地址>:<配置的端口号>/`

核心技能是 `execute_mcp_json_rpc`。要使用此技能，您需要发送一个 A2A `Message`，其 `parts` 列表中包含一个 `DataPart`。该 `DataPart.data` 字典应包含以下字段：

*   `mcp_target_url` (字符串, 必需): 目标 MCP 服务的基础 URL (例如, `http://localhost:8000`)。
*   `mcp_method` (字符串, 必需): 要调用的 MCP JSON-RPC 方法 (例如, `prompts/list`, `resources/read`)。
*   `mcp_params` (字典, 必需): MCP 方法所需的参数字典。
*   `mcp_request_path` (字符串, 可选, 默认为 `/messages/`): MCP 服务上发送请求的具体路径 (例如, `/messages/`, `/v1/mcp/`)。**重要提示:** 此路径会附加到 `mcp_target_url` 之后。
*   `mcp_request_id` (字符串或整数, 可选): MCP 请求的可选 ID。如果未提供，则会自动生成一个。

**`DataPart.data` 结构示例:**
```json
{
  "mcp_target_url": "http://some-mcp-service.example.com",
  "mcp_request_path": "/api/mcp_endpoint/", 
  "mcp_method": "tools/call",
  "mcp_params": {
    "name": "my_tool_name",
    "arguments": {
      "arg1": "value1",
      "arg2": 123
    }
  },
  "mcp_request_id": "client-req-001"
}
```
(关于更完整的 A2A 请求结构，请参考 A2A 协议规范以及项目中的 `/examples` 目录。)

## 代码示例

关于如何与此转换器交互的详细示例，包括示例 A2A 请求负载，可以在本仓库的 `/examples` 目录中找到。
<!-- 如果有帮助，可以链接到具体的示例文件 -->

## 测试运行

运行自动化测试:
```bash
# 确保已安装开发依赖 (例如 pytest)
# poetry install --with dev
# 或 pip install pytest httpx 等

poetry run pytest tests/
# 或
python -m pytest tests/
```
(请根据您的实际测试设置调整测试命令。)

## 如何贡献 (可选)

欢迎参与贡献！请阅读 `CONTRIBUTING.md` 文件以了解参与此项目的详细信息 (如果您创建了此文件)。
或者，您可以在此处列出基本步骤：
1. Fork 本仓库。
2. 创建一个新的分支 (`git checkout -b feature/YourFeature`)。
3. 进行您的修改。
4. 提交您的修改 (`git commit -m 'Add some feature'`)。
5. 将分支推送到远程仓库 (`git push origin feature/YourFeature`)。
6. 创建一个 Pull Request。

## 项目许可证

本项目采用 MIT 许可证 - 详细信息请参阅 [LICENSE](LICENSE) 文件。
