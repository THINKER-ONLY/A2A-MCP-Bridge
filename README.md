# A2A-to-MCP Translator (Adapter) - 转换器项目

[![许可证: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
<!-- 如果您有其他徽章，例如构建状态、测试覆盖率等，请在此处添加 -->

## 项目概述

A2A-to-MCP Translator (Adapter) 是一个基于 Python 的网关服务，充当**代理间协议 (A2A)** 与遵循**模型上下文协议 (MCP)** 的服务之间的桥梁。其主要目标是使 A2A 客户端能够通过将 A2A 任务转换为 MCP JSON-RPC 请求，并将 MCP 响应转换回 A2A 任务结果，从而与基于 MCP 的服务进行无缝交互。

该转换器 (`MCPGatewayAgent`) 允许通过 A2A 协议进行通信的 AI 代理利用各种支持 MCP 的工具和平台的功能，而无需直接实现 MCP 客户端逻辑。

## 主要特性

*   **A2A 服务器端点**: 实现了一个符合 A2A 规范的服务器端点 (`/`)，用于接收任务。
*   **Agent Card**: 提供了一个 A2A Agent Card (`/.well-known/agent.json`)，详细说明了转换器的能力和技能。
*   **MCP 请求转换**: 解析 A2A `DataPart` 输入，以提取 MCP 调用的参数（目标 URL、路径、方法、参数）。
*   **MCP 通信**: 使用 `httpx` 向指定的目标 MCP 服务发送 JSON-RPC 请求。
*   **响应适配**: 将 MCP 响应（成功或错误）格式化回 A2A `TaskStatus` 和 `Artifacts`。
*   **异步处理**: 使用 `asyncio`, `starlette`, 和 `httpx` 构建，以实现非阻塞 I/O。
*   **命令行配置**: 服务主机和端口可以通过命令行参数进行配置。
*   **端到端示例**: 包含一个演示脚本 (`examples/run_demo.sh`)，用于启动模拟 MCP 服务、Adapter 服务和 A2A 客户端，以展示完整流程。

## 技术栈与核心依赖

*   Python 3.12+
*   Poetry (用于依赖管理和打包)
*   Starlette (用于构建 ASGI 应用)
*   Uvicorn (ASGI 服务器)
*   HTTPX (异步 HTTP 客户端)
*   Pydantic (数据验证与模型定义)
*   Click (用于构建命令行界面)
*   **A2A 协议栈**: 基于 `@A2A/samples/python/common/` (vendored in `src/vendor/A2A/`)
*   **MCP 协议栈**: 基于 `@python-sdk/src/mcp/` (vendored in `src/vendor/MCP/`)

## 先决条件

*   Python 3.12 或更高版本。
*   Poetry (推荐，用于依赖管理和运行脚本)。

## 安装步骤

1.  **克隆代码仓库:**
    ```bash
    # git clone https://github.com/<您的GitHub用户名>/<仓库名称>.git # 根据实际情况替换
    cd Adapter
    ```

2.  **创建并激活虚拟环境 (推荐):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/macOS
    # .venv\Scripts\activate  # Windows
    ```

3.  **安装依赖 (使用 Poetry):**
    ```bash
    poetry install
    ```

## 运行服务

Adapter 服务可以通过 `src.translator` 模块启动，并接受命令行参数进行配置。

```bash
python -m src.translator --host <您的主机地址> --port <您的端口号>
```
例如:
```bash
python -m src.translator --host 127.0.0.1 --port 8000
```
*   `--host`: 服务监听的主机地址 (默认: `127.0.0.1`)。
*   `--port`: 服务监听的端口号 (默认: `8000`)。

## 运行端到端演示

项目包含一个完整的端到端演示脚本，位于 `examples/run_demo.sh`。该脚本会自动：
1.  启动一个模拟的下游 MCP 服务。
2.  启动 `MCPGatewayAgent` (Adapter 服务)。
3.  运行一个 A2A 客户端 (`examples/A2A/call_adapter.py`) 向 Adapter 发送任务。
4.  输出交互过程和最终结果。

要运行演示：
```bash
cd examples
./run_demo.sh
```
强烈建议通过此脚本来理解和测试系统的完整工作流程。

## 与 Agent 交互

### Agent Card
Agent Card 提供了关于此 Agent 的元数据。可以通过以下地址访问：
`http://<配置的主机地址>:<配置的端口号>/.well-known/agent.json`

例如，如果服务运行在 `http://127.0.0.1:8000`：
`http://127.0.0.1:8000/.well-known/agent.json`

### 发送任务 (Execute MCP JSON-RPC Skill)
任务以 A2A 协议消息的形式发送到 Adapter 服务的根端点 (`/`)。

核心技能是 `execute_mcp_json_rpc`。要使用此技能，您需要发送一个 A2A `Message`，其 `parts` 列表中包含一个 `DataPart`。该 `DataPart.data` 字典应包含以下字段：

*   `mcp_target_url` (字符串, 必需): 目标 MCP 服务的基础 URL (例如, `http://localhost:8001`)。
*   `mcp_method` (字符串, 必需): 要调用的 MCP JSON-RPC 方法 (例如, `tools/call`, `prompts/list`)。
*   `mcp_params` (字典, 必需): MCP 方法所需的参数字典。
*   `mcp_request_path` (字符串, 可选, 默认为空字符串 `""`): MCP 服务上发送请求的具体路径 (例如, `/mcp`, `/v1/api/mcp/`)。如果提供，此路径会附加到 `mcp_target_url` 之后。如果为空，则直接使用 `mcp_target_url`。
*   `mcp_request_id` (字符串或整数, 可选): MCP 请求的可选 ID。如果未提供，Adapter 会自动生成一个。

**`DataPart.data` 结构示例:**
```json
{
  "mcp_target_url": "http://localhost:8001",
  "mcp_request_path": "/mcp", 
  "mcp_method": "tools/call",
  "mcp_params": {
    "model": "some-model-name",
    "messages": [
      {
        "role": "user",
        "content": "你好，世界！"
      }
    ]
  }
}
```
Adapter 服务会将 MCP 服务的响应封装在返回的 A2A `Task` 的 `artifacts` 列表中。每个 `Artifact` 将包含一个 `DataPart`，其 `data` 字段即为 MCP 服务返回的 JSON-RPC 响应体（或错误信息）。

## 项目结构

核心逻辑位于 `src/translator/` 目录下：
*   `__main__.py`: 服务启动入口，处理命令行参数，初始化并运行 `A2AServer`。
*   `task_manager.py`: 包含 `MCPGatewayAgentTaskManager` 类，负责处理 A2A 任务到 MCP 请求的转换和反向转换。
*   `agent_card.py`: 定义并提供 Agent Card 的内容。
*   `mcp_client.py`: (已移除，逻辑合并到 `task_manager.py`) 包含发送 HTTP 请求到 MCP 服务的逻辑。

Vendored 代码 (第三方库的本地副本):
*   `src/vendor/A2A/`: 包含 A2A 协议相关的类型定义和服务器基础组件。
*   `src/vendor/MCP/`: 包含 MCP 协议相关的类型定义。

## 测试运行

项目使用 `pytest`进行单元测试。测试用例位于 `tests/` 目录下。

确保已安装开发依赖:
```bash
poetry install --with dev  # 如果测试依赖在 dev 组
# 或 poetry install (如果测试依赖是主依赖的一部分)
```

运行测试:
```bash
poetry run pytest
# 或者，如果 pytest 在PATH中:
# pytest
```

## 如何贡献 (可选)

欢迎参与贡献！
1. Fork 本仓库。
2. 创建一个新的特性分支 (`git checkout -b feature/YourAmazingFeature`)。
3. 进行您的修改。
4. 确保所有测试通过。
5. 提交您的修改 (`git commit -m 'Add some AmazingFeature'`)。
6. 将分支推送到远程仓库 (`git push origin feature/YourAmazingFeature`)。
7. 创建一个 Pull Request。

## 项目许可证

本项目采用 MIT 许可证 - 详细信息请参阅 [LICENSE](LICENSE) 文件。
