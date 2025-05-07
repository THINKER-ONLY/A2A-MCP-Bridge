# MCPGatewayAgent 设计文档

## 1. 项目目标

`MCPGatewayAgent` 项目的主要目标是创建一个独立的 A2A (Agent-to-Agent) 代理，该代理充当 A2A 协议与任何兼容 MCP (Model Context Protocol) 的服务之间的通用桥梁。此代理将使 A2A 客户端（包括编排器代理）能够通过标准化的 A2A 接口与各种基于 MCP 的服务（例如代码生成工具、文件系统管理器）进行交互并利用其功能。

更广泛的愿景是促进一个多智能体系统，其中主编排器代理可以分解复杂任务（如自动化代码开发）并分发子任务。当这些子任务需要与 MCP 服务交互时，它们将被路由通过 `MCPGatewayAgent`。

## 2. 架构概览

拟议的系统架构采用分层方法：

1.  **用户/初始客户端**: 与主代理交互，提供高级目标。
2.  **主代理/编排器**:
    *   理解用户需求。
    *   执行任务规划和分解。
    *   将需要 MCP 操作的子任务转换为特定的 MCP 命令描述。
    *   构建封装这些 MCP 命令描述的 A2A `Task` 请求。
    *   将这些 A2A `Task` 请求发送给 `MCPGatewayAgent`。
3.  **`MCPGatewayAgent` (本项目)**:
    *   一个专用的 A2A 代理。
    *   从主代理接收 A2A `Task` 请求。
    *   从 A2A `Task` 中解析 MCP 命令描述。
    *   通过向目标 MCP 服务发送 MCP JSON-RPC 请求来执行这些命令。
    *   接收 MCP JSON-RPC 响应。
    *   将 MCP 响应打包回 A2A `TaskResult` 对象。
    *   通过 A2A 协议将结果返回给主代理。
4.  **MCP 服务 (例如来自 `@python-sdk` 的 `My_mcp`)**:
    *   符合模型上下文协议的下游服务。
    *   从 `MCPGatewayAgent` 接收 MCP JSON-RPC 请求。
    *   执行底层操作（文件 I/O、代码生成逻辑等）。
    *   返回 MCP JSON-RPC 响应。

此架构确保主代理可以在更高级别的抽象上操作，而无需了解 MCP 的复杂性，同时 MCP 服务与 A2A 生态系统保持解耦。`MCPGatewayAgent` 集中处理 A2A 到 MCP 的协议转换。

## 3. `MCPGatewayAgent` 详细设计

### 3.1. 核心职责

*   作为符合规范的 A2A 代理，可通过其 AgentCard 被发现。
*   接收包含调用下游 MCP 服务操作指令的 A2A `Task` 请求。
*   解析这些指令以确定目标 MCP 服务 URL、要调用的 MCP 方法以及该方法的参数。
*   构建有效的 MCP JSON-RPC 请求消息。
*   将这些 MCP 请求分派到指定的 MCP 服务端点（主要通过 HTTP POST）。
*   从下游服务接收 MCP JSON-RPC 响应。
*   将 MCP 响应（包括成功和错误）转换为 A2A `TaskResult` 格式，包括 `Artifacts` 和 `TaskStatus`。
*   优雅地处理通信错误。

### 3.2. `AgentCard` 定义 (`MCPGatewayAgentCard`)

*   **`name`**: `"MCP Gateway Agent"` (MCP 网关代理)
*   **`description`**: `"一个通用的 A2A 代理，充当网关，用于将请求转发到任何符合 MCP 规范的服务并接收其响应。"`
*   **`url`**: `http://<mcp_gateway_agent_host>:<mcp_gateway_agent_port>/` (此代理监听 A2A 请求的端点)
*   **`version`**: `"1.0.0"`
*   **`capabilities`** (能力):
    *   `streaming` (流式传输): `False` (初始版本；如果 MCP 服务支持流式传输并且需要，则可以扩展)
    *   `pushNotifications` (推送通知): `False` (初始版本)
*   **`defaultInputModes`** (默认输入模式): `["data"]`
*   **`defaultOutputModes`** (默认输出模式): `["data"]`
*   **`skills`** (技能):
    *   **技能 1: `execute_mcp_command`** (执行 MCP 命令)
        *   **`id`**: `"execute_mcp_command"`
        *   **`name`**: `"Execute MCP Command"`
        *   **`description`**: `"在目标 MCP 服务上使用给定参数执行指定的 MCP JSON-RPC 方法。命令详细信息在输入的 DataPart 中提供。"`
        *   **`inputModes`**: `["data"]`
        *   **`outputModes`**: `["data"]`
        *   **输入 `DataPart` 结构 (用于 A2A Task 的 `message.parts` 数组):**
            ```json
            {
              "type": "data",
              "data": {
                "mcp_target_url": "string (例如, http://localhost:8000)",
                "mcp_request_path": "string (例如, /messages/, 可选, 默认为 /messages/)",
                "mcp_method": "string (例如, tools/call, resources/read)",
                "mcp_params": "object (表示 MCP 方法参数的 JSON 对象)",
                "mcp_request_id": "string | integer (可选, MCP 请求的 ID)"
              }
            }
            ```
            *`mcp_params` 用于 `tools/call` 的示例:*
            ```json
            {
              "name": "mcp_tool_name_to_call",
              "arguments": { "arg1": "value1", "arg2": 123 }
            }
            ```
            *`mcp_params` 用于 `resources/read` 的示例:*
            ```json
            {
              "uri": "mcp_resource_uri_to_read"
            }
            ```
        *   **输出 `DataPart` 结构 (用于 A2A TaskResult 的 `artifacts` 数组):**
            ```json
            {
              "type": "data",
              "data": {
                "mcp_request_id_echo": "string | integer (已发送 MCP 请求的 ID)",
                "mcp_response_id": "string | integer (来自 MCP JSON-RPC 响应的 ID)",
                "mcp_result": "object (MCP JSON-RPC 结果对象, 成功时存在)",
                "mcp_error": "object (MCP JSON-RPC 错误对象, 失败时存在)"
              }
            }
            ```
        *   **A2A 请求示例 (简化版, 显示 `DataPart`):**
            在位于 `http://localhost:8001` 的 MCP 服务上调用工具 `my_tool`：
            ```json
            // A2A Task -> message -> parts 数组内部
            {
              "type": "data",
              "data": {
                "mcp_target_url": "http://localhost:8001",
                "mcp_method": "tools/call",
                "mcp_params": {
                  "name": "my_tool",
                  "arguments": { "input_param": "some_value" }
                }
              }
            }
            ```

### 3.3. `MCPGatewayAgentTaskManager` 实现要点

*   `MCPGatewayAgentTaskManager` 类将继承自 `common.server.task_manager.InMemoryTaskManager`。
*   主要实现的方法是 `async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:`。
*   **`on_send_task` 逻辑流程**:
    1.  对 A2A `request` 进行初始验证（例如，确保 `message.parts` 包含预期的 `DataPart`）。
    2.  从输入的 `DataPart` 中提取 MCP 调用参数 (`mcp_target_url`, `mcp_request_path`, `mcp_method`, `mcp_params`, `mcp_request_id`)。
    3.  使用来自 `@python-sdk/src/mcp/types.py` 的类型构建 MCP JSON-RPC 请求对象。
        *   如果未提供或希望使用新的 ID，则为 MCP 请求生成一个唯一的 ID。
        *   MCP JSON-RPC 请求的 `params` 字段将是从 A2A `DataPart` 中提取的 `mcp_params` 对象。
    4.  通过组合 `mcp_target_url` 和 `mcp_request_path` (如果未提供 `mcp_request_path`，则使用默认值，例如根据 `FastMCP` 默认为 `/messages/`) 来确定完整的目标 HTTP URL。
    5.  使用 HTTP 客户端库（例如 `httpx.AsyncClient`）向完整的目标 URL 发送 HTTP POST 请求。
        *   请求体将是 JSON 序列化的 MCP JSON-RPC 请求对象。
        *   将 `Content-Type` 标头设置为 `application/json`。
    6.  等待并接收来自 MCP 服务的 HTTP 响应。
    7.  处理 HTTP 级别的错误（例如，连接错误，未携带 JSON-RPC 错误的 4xx/5xx 状态码）。
    8.  如果 HTTP 响应成功，则将其 JSON 主体解析为 MCP JSON-RPC 响应（或错误）对象。
    9.  构建 A2A `TaskStatus` (`COMPLETED` 或 `FAILED`)。
    10. 构建 A2A `Artifact` 列表。它将包含一个封装了 `mcp_response_id` 以及 `mcp_result` 或 `mcp_error` 的 `DataPart`。
    11. 使用 `await self.update_store(...)` 更新任务存储。
    12. 返回包含 A2A `TaskResult` 的 `SendTaskResponse`。
*   **错误处理**:
    *   区分 A2A 请求验证错误、调用 MCP 时的网络错误、MCP 服务返回 MCP JSON-RPC 错误以及意外错误。
    *   将这些适当地映射到 A2A `TaskState.FAILED`，并在输出 `DataPart` 的 `mcp_error` 字段中或在 `SendTaskResponse` 的 A2A `JSONRPCError` 中包含错误详细信息。

### 3.4. 依赖项

*   来自 `@A2A/samples/python/common/` 的 A2A `common` 模块（主要用于 `types.py`、`server.py` 的 `A2AServer` 和 `task_manager.py` 的 `InMemoryTaskManager`）。
*   来自 `@python-sdk/src/mcp/types.py` 的 MCP 类型定义（用于构建 MCP JSON-RPC 请求和解析响应）。
*   `httpx`：用于向 MCP 服务发出异步 HTTP 请求。
*   Pydantic (已经是 A2A 和 MCP SDK 的依赖项)。

### 3.5. 项目文件结构 (Project File Structure)

```text
@Adapter/
├── src/
│   └── translator/         # 主要的 Python 包源代码
│       ├── __init__.py
│       ├── agent_card.py     # (可选)
│       ├── task_manager.py
│       ├── mcp_client.py     # (推荐)
│       └── __main__.py       # MCPGatewayAgent 启动脚本
├── examples/                 # (推荐) 示例代码目录
│   ├── __init__.py           # (可选) 使 examples 成为一个可导入的包
│   ├── sample_mcp_service/   # 一个简单的、本地运行的 MCP 服务示例
│   │   ├── __init__.py
│   │   ├── main.py           # 启动示例 MCP 服务的脚本
│   │   └── agent.py          # 示例 MCP 服务的简单逻辑
│   ├── a2a_client_example.py # 一个调用 MCPGatewayAgent 的 A2A 客户端示例脚本
│   └── README.md             # 说明如何运行这些示例
├── tests/
│   ├── __init__.py
│   └── test_task_manager.py
├── pyproject.toml
├── README.md                 # 项目顶层 README
├── DESIGN.md                 # 本设计文档
├── .gitignore
└── .env
```

**各文件/目录说明：**

*   **`src/translator/`**: 存放 `MCPGatewayAgent` 所有核心 Python 源代码的包目录。
    *   **`__init__.py`**: 将 `translator` 标记为一个 Python 包。
    *   **`agent_card.py`** (可选): 如果 `AgentCard` 定义复杂，可单独存放于此。可提供一个函数返回配置好的 `AgentCard` 对象。
    *   **`task_manager.py`**: 包含 `MCPGatewayAgentTaskManager(InMemoryTaskManager)` 类的定义，实现核心的 A2A 任务处理和 MCP 调用转换逻辑。
    *   **`mcp_client.py`** (推荐): 封装与下游 MCP 服务进行实际通信的细节 (如构造和发送 HTTP POST 请求，处理 MCP JSON-RPC 消息)。`MCPGatewayAgentTaskManager` 将调用此模块的功能。
    *   **`__main__.py`**: 代理服务器的启动入口。实例化并配置 `A2AServer`、`AgentCard` 和 `MCPGatewayAgentTaskManager`。
*   **`examples/`** (推荐):
    *   **`sample_mcp_service/`**: 用于测试 `MCPGatewayAgent` 的一个轻量级示例 MCP 服务。
        *   `main.py`: 启动此示例 MCP 服务。
        *   `agent.py`: 定义此示例 MCP 服务的简单工具或资源。
    *   **`a2a_client_example.py`**: 演示如何通过 A2A 协议与 `MCPGatewayAgent` 交互以调用下游 MCP 服务的客户端脚本。
    *   **`README.md`**: 关于如何设置和运行示例的说明。
*   **`tests/`**: 存放单元测试和集成测试代码。
*   **`pyproject.toml`**: 定义项目元数据和依赖项 (如 `httpx`, A2A `common` 模块的引用, MCP SDK `types` 的引用)。
*   **`README.md`**: 项目的总体说明、安装、配置和运行指南。
*   **`DESIGN.md`**: 本详细设计文档。
*   **`.gitignore`**: 指定 Git 应忽略的文件。
*   **`.env`** (可选): 用于本地开发时存储环境变量 (如默认端口)。

## 4. 与下游 MCP 服务的交互

*   **通信协议**: HTTP POST。
*   **请求体**: JSON-RPC 2.0 消息，其 `method` 和 `params` 由 MCP 规范定义（例如，`method: "tools/call"`, `params: {"name": "tool_name", "arguments": {...}}`）。
*   **目标端点**: 根据 A2A 请求中提供的 `mcp_target_url` 和 `mcp_request_path` 动态确定。对于基于 `FastMCP` 的服务，`mcp_request_path` 通常默认为 `/messages/` 或 `/sse`（尽管对于非流式 RPC 调用，专用的消息路径更典型）。
*   **认证**:
    *   初始范围：假设没有认证或简单的基于令牌的认证，其中令牌可以通过 A2A `DataPart` 内的 `mcp_headers` 字段传递，然后将其添加到对 MCP 服务的 HTTP 请求中。
    *   未来：如果 MCP 服务需要，可以研究更复杂的 OAuth 或其他机制。

## 5. 未来考虑/可选功能

*   **支持流式 MCP 交互**: 如果 MCP 服务支持某些操作的流式响应（例如通过 SSE），并且 A2A 客户端需要此功能，则需要实现 `MCPGatewayAgent` 的 `on_send_task_subscribe` 方法来处理 A2A SSE 到 MCP SSE/流式传输的桥接。
*   **MCP 服务能力发现**: 代理可以有选择地在目标 MCP 服务上调用 `initialize`、`tools/list` 和 `resources/list` 以发现其能力并验证传入请求，甚至动态调整其自身 `AgentCard` 报告的技能（更复杂）。
*   **缓存 MCP 服务响应**: 对于幂等的 MCP 操作，缓存可以提高性能。
*   **高级认证/凭据管理**: 安全地管理访问不同下游 MCP 服务的凭据。
*   **已知 MCP 服务的配置**: 允许为常用 MCP 服务预配置别名或默认参数。

本文档概述了 `MCPGatewayAgent` 的初始设计和目标。它将随着开发的进展而完善。 