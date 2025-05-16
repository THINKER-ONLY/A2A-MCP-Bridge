#!/usr/bin/env python
import asyncio
import json
import httpx
import argparse
import uuid
from typing import Dict, Any, List

# 根据您项目 vendor 目录的实际结构调整导入路径
try:
    # 从 src.vendor.A2A.types 导入 A2A 模型类
    # 需要额外导入 Message 和 TaskSendParams
    from src.vendor.A2A.types import (
        Task, DataPart, SendTaskRequest, SendTaskResponse,
        Message, TaskSendParams # 添加这两个导入
        # Input 和 Metadata 不是独立类，移除它们
    )
except ImportError:
    # 更新错误消息以反映正确的路径结构
    print("错误：无法从 src.vendor.A2A.types 导入 A2A 模型类。")
    print("请确保您的 Python 环境可以找到这些模块，或者调整此脚本中的导入路径。")
    print("检查点：")
    print("  1. Adapter/src/vendor/ 目录下是否存在 \'A2A\' (大写) 目录？")
    print("  2. \'A2A\' 目录下是否存在名为 \'types.py\' 的文件？")
    print("  3. \'types.py\' 文件中是否定义了 Task, DataPart, SendTaskRequest, SendTaskResponse, Message, TaskSendParams 类？") # 更新检查列表
    print("  4. 是否从 Adapter 项目的根目录运行此脚本 (例如 \'python -m examples.A2A.call_adapter\')，或者已将 Adapter/src 添加到 PYTHONPATH？")
    exit(1)

DEFAULT_ADAPTER_URL = "http://localhost:8000"  # 默认 Adapter 服务的基础地址
DEFAULT_MCP_TARGET_URL = "http://localhost:8001/mcp" # 默认模拟 MCP 服务地址

def build_mcp_payload(target_url_full_path: str, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建要放入 DataPart 的 MCP 调用载荷。
    """
    return {
        "mcp_target_url": target_url_full_path, # 使用 mcp_target_url 并传递完整路径
        "mcp_method": method,
        "mcp_params": params,
        # "mcp_request_path": "" # 可选：如果 task_manager 需要它来避免附加默认路径
    }

def build_a2a_request_payload(mcp_data: Dict[str, Any]) -> SendTaskRequest:
    """
    构建发送给 Adapter 的 A2A SendTaskRequest。
    核心是将 MCP 调用信息封装在 DataPart 中。
    """
    task_id = str(uuid.uuid4())
    mcp_data_part = DataPart(
        mimetype="application/json",
        # 注意: A2A types.py 中的 DataPart 定义 data 为 dict[str, Any], 而不是 bytes
        # 所以这里应该直接传递 dict，而不是 json.dumps().encode()
        data=mcp_data
    )

    # 构造 Message 对象
    message = Message(role="user", parts=[mcp_data_part])

    # 构造 TaskSendParams 对象
    task_params = TaskSendParams(
        id=task_id,
        message=message,
        # 可以将元数据放在这里
        metadata={"client": "example_a2a_caller"}
    )

    # 构造 SendTaskRequest 对象
    request_payload = SendTaskRequest(params=task_params)
    return request_payload


async def call_adapter(adapter_base_url: str, request_payload: SendTaskRequest):
    """
    使用 httpx 异步调用 Adapter 服务。
    """
    target_url = adapter_base_url.rstrip('/') + "/" # 请求应发送到根路径
    try:
        async with httpx.AsyncClient() as client:
            print(f"正在向 Adapter 发送请求: {target_url}")
            # A2A 规范通常要求 POST 请求体是 JSON 格式
            # 使用 pydantic 的 model_dump_json 来序列化
            request_json_str = request_payload.model_dump_json()
            print("--- 请求体 (A2A SendTaskRequest) ---")
            print(request_json_str)
            print("------------------------------------")

            response = await client.post(
                target_url, # 使用拼接好的 URL
                content=request_json_str,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status() # 如果状态码不是 2xx，则抛出异常

            print("--- Adapter 响应 ---")
            response_data = response.json()
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            print("--------------------")

            # 尝试将响应解析回 SendTaskResponse 模型 (可选)
            try:
                a2a_response = SendTaskResponse.model_validate(response_data)
                print("\n成功解析 Adapter 响应为 SendTaskResponse。")
                # 这里可以进一步处理 a2a_response 对象，例如检查 task.status 或 artifacts
                # 注意：SendTaskResponse 的 result 是 Task 对象
                if a2a_response.result:
                    task_result = a2a_response.result
                    print(f"任务状态: {task_result.status.state.value if task_result.status else '未知'}")
                    if task_result.artifacts:
                        print("\n--- 响应中的 Artifacts ---")
                        for i, artifact in enumerate(task_result.artifacts):
                            print(f"Artifact {i+1}: Name={artifact.name}, Index={artifact.index}")
                            if artifact.parts:
                                for j, part in enumerate(artifact.parts):
                                    print(f"  Part {j+1}: Type={part.type}, Mimetype={getattr(part, 'mimetype', 'N/A')}") # Mimetype可能不存在于所有 Part 类型
                                    # 尝试打印 Part 内容 (注意 DataPart.data 是 dict)
                                    part_data = getattr(part, 'data', None) or getattr(part, 'text', None) or getattr(part, 'file', None)
                                    if isinstance(part_data, dict):
                                         print(f"    Data (JSON):\n{json.dumps(part_data, indent=2, ensure_ascii=False)}")
                                    elif isinstance(part_data, str):
                                         print(f"    Text:\n{part_data}")
                                    elif part_data: # 假设是 FileContent
                                         print(f"    File: Name={part_data.name}, Mime={part_data.mimeType}, URI={part_data.uri}, Bytes provided={bool(part_data.bytes)}")

                        print("-------------------------")


            except Exception as e:
                print(f"\n警告：无法将响应解析为 SendTaskResponse 或处理其内容: {e}")

    except httpx.HTTPStatusError as e:
        print(f"\n错误：Adapter 返回 HTTP 错误状态 {e.response.status_code}")
        print(f"响应内容: {e.response.text}")
    except httpx.RequestError as e:
        print(f"\n错误：无法连接到 Adapter 服务: {e}")
    except Exception as e:
        print(f"\n发生意外错误: {e}")

async def main():
    parser = argparse.ArgumentParser(description="示例 A2A 客户端，用于调用 A2A-to-MCP Adapter")
    parser.add_argument(
        "--adapter-url",
        default=DEFAULT_ADAPTER_URL,
        help=f"Adapter 服务的根 URL (默认: {DEFAULT_ADAPTER_URL}), /tasks 将被自动追加以发送任务。"
    )
    parser.add_argument(
        "--mcp-target-url",
        default=DEFAULT_MCP_TARGET_URL,
        help=f"目标 MCP 服务的 URL (默认: {DEFAULT_MCP_TARGET_URL})"
    )
    parser.add_argument(
        "--mcp-method",
        default="tools/call",
        help="要调用的 MCP 方法 (默认: tools/call)"
    )
    parser.add_argument(
        "--mcp-param",
        action='append',
        help="MCP 参数，格式为 key=value (可以多次使用)"
    )

    args = parser.parse_args()

    # 解析 MCP 参数
    mcp_params = {}
    if args.mcp_param:
        for param in args.mcp_param:
            if '=' in param:
                key, value = param.split('=', 1)
                # 尝试将 value 解析为 JSON，如果失败则视为字符串
                try:
                    mcp_params[key] = json.loads(value)
                except json.JSONDecodeError:
                    mcp_params[key] = value
            else:
                print(f"警告：忽略格式错误的 MCP 参数 '{param}'，请使用 key=value 格式。")

    # 如果没有通过命令行提供参数，使用一个默认的示例参数
    if not mcp_params:
        mcp_params = {
            "model": "some-model-name",
            "messages": [
                {"role": "user", "content": "你好，世界！"}
            ]
        }
        print("未使用命令行 --mcp-param 参数，将使用默认 MCP 参数:")
        print(json.dumps(mcp_params, indent=2, ensure_ascii=False))


    # 1. 构建 MCP 载荷 (包含 mcp_target_url, mcp_method, mcp_params)
    mcp_payload = build_mcp_payload(
        target_url_full_path=args.mcp_target_url, # 将完整 MCP URL 传递给新的函数签名
        method=args.mcp_method,
        params=mcp_params
    )

    # 2. 构建 A2A 请求 (将 MCP 载荷作为 DataPart 的 data)
    a2a_request = build_a2a_request_payload(mcp_payload)

    # 3. 调用 Adapter
    await call_adapter(args.adapter_url, a2a_request)

if __name__ == "__main__":
    asyncio.run(main()) 