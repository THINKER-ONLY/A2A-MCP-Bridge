# A2A-to-MCP Adapter 示例

此目录包含运行 A2A-to-MCP Adapter 端到端演示所需的文件。

## 目录结构

- `MCP/service.py`: 一个简单的模拟 MCP 服务，用于接收 Adapter 转发的请求。
- `A2A/call_adapter.py`: 一个示例 A2A 客户端，用于向 Adapter 服务发送包含 MCP 调用参数的任务。
- `run_demo.sh`: 用于一键启动模拟 MCP 服务、Adapter 服务，并运行示例 A2A 客户端的脚本。
- `requirements.txt`: 运行此目录下所有示例代码所需的 Python 依赖。

## 运行演示

1.  **确保 Adapter 服务已安装:** 请确保您已按照项目根目录 `README.md` 的说明安装了 Adapter 项目本身及其依赖。
2.  **安装示例依赖:** (在 `examples` 目录下执行)
    ```bash
    pip install -r requirements.txt
    ```
3.  **(重要) 检查/修改 Adapter 启动命令:** 打开 `run_demo.sh` 文件，找到启动 Adapter 服务的行 (标记为 `!!! 注意` 的地方)，确保该命令能正确启动您的 Adapter 服务 (可能需要调整路径、端口或添加配置文件参数)。
4.  **赋予脚本执行权限:**
    ```bash
    chmod +x run_demo.sh
    ```
5.  **运行演示脚本:**
    ```bash
    ./run_demo.sh
    ```

脚本将依次启动后台服务，然后运行客户端。观察终端输出，您应该能看到客户端发送请求、Adapter 处理请求（如果 Adapter 有日志输出）、模拟 MCP 服务收到请求并返回响应、最终客户端收到 Adapter 返回的结果。

## 关于示例代码

- `MCP/service.py`: 这个模拟服务非常基础，主要用于响应 `tools/call` 方法。您可以根据需要修改它以模拟更复杂的行为。
- `A2A/call_adapter.py`: 这个客户端脚本的核心在于 `build_a2a_request_payload` 函数，它展示了如何将 MCP 调用信息封装在发送给 Adapter 的 A2A 请求的 `DataPart` 中。请仔细阅读该函数的实现和注释。
