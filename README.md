# A2A-to-MCP Translator Agent (MCPGatewayAgent)

本项目 (`@Adapter`) 实现了一个 A2A (Agent-to-Agent) 代理，作为连接 A2A 协议和 MCP (Model Context Protocol) 服务的通用网关。

详细设计请参见 [DESIGN.md](DESIGN.md)。

## 功能

- 接收通过 A2A 协议发送的、旨在调用下游 MCP 服务的任务。
- 解析任务中指定的 MCP 服务目标 (URL) 和 MCP 操作指令 (方法名、参数)。
- 向目标 MCP 服务发送符合 MCP JSON-RPC 规范的请求 (通常通过 HTTP POST)。
- 接收 MCP 服务的响应。
- 将 MCP 响应（成功或错误）转换回 A2A `TaskResult` 格式并返回给调用方。

## 环境设置

1.  **Conda 环境**: 建议使用 Conda 创建并激活一个 Python >= 3.12 的虚拟环境 (例如 `adapter_env`)。
    ```bash
    conda create --name adapter_env python=3.12 -y
    conda activate adapter_env
    ```
2.  **安装依赖**: 参考 `pyproject.toml` 文件。核心依赖包括 `httpx`, `pydantic`, `uvicorn`, `starlette` 等。开发依赖包括 `pytest`, `ruff`, `mypy`。
    ```bash
    pip install -e .[dev]  # (如果项目配置为可编辑安装且包含dev依赖组)
    # 或者分别安装核心依赖和开发依赖
    ```
3.  **PYTHONPATH 设置**: 为了使本项目能正确导入本地的 `@A2A/samples/python/common/` 和 `@python-sdk/src/mcp/` 模块，需要将这两个项目的相应路径添加到 `PYTHONPATH` 环境变量中。具体方法请参见 `DESIGN.md` 或开发环境配置说明。
    推荐在本项目根目录下创建 `.env` 文件，并添加如下内容 (请替换为您的实际路径):
    ```env
    PYTHONPATH=/path/to/A2A/samples/python:/path/to/python-sdk/src:${PYTHONPATH}
    ```
    并在 IDE (如 VS Code) 或运行脚本前加载此 `.env` 文件 (例如使用 `python-dotenv`)。

## 运行 Agent

```bash
python src/translator/__main__.py --host <your_host> --port <your_port>
```
默认情况下，可以运行 `python src/translator/__main__.py` (host默认为 `localhost`, port默认为 `8000`，具体请参见 `__main__.py` 中的配置)。

## 运行示例

请参见 `examples/README.md` 中的说明来运行端到端示例，包括一个示例 MCP 服务和一个调用本 Agent 的 A2A 客户端。

## 开发

- **代码风格与检查**: 使用 Ruff 进行 linting 和 formatting。配置见 `pyproject.toml`。
- **类型检查**: 使用 MyPy。配置见 `pyproject.toml`。
- **测试**: 使用 Pytest。测试文件位于 `tests/` 目录下。
  ```bash
  pytest
  ```
