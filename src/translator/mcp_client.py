import httpx
from typing import Dict, Any, Optional

async def send_mcp_request(
    target_url: str,  # 完整的 URL，包括路径
    mcp_json_rpc_request_dict: Dict[str, Any],  # 序列化为字典的 MCP JSON-RPC 请求
    headers: Optional[Dict[str, str]] = None,  # 可选的额外 HTTP 头
    timeout: float = 30.0  # 请求超时时间（秒）
) -> Dict[str, Any]:  # 返回从 MCP 服务解析的 JSON 响应字典
    """
    向 MCP 服务发送 JSON-RPC 请求并返回响应。

    Args:
        target_url: 目标 MCP 服务的完整 URL（包括路径）
        mcp_json_rpc_request_dict: 序列化为字典的 MCP JSON-RPC 请求
        headers: 可选的额外 HTTP 头
        timeout: 请求超时时间（秒）

    Returns:
        Dict[str, Any]: MCP 服务的 JSON 响应

    Raises:
        httpx.HTTPError: 当发生 HTTP 错误时（如 4xx/5xx 状态码）
        httpx.RequestError: 当发生网络错误时
        ValueError: 当响应不是有效的 JSON 时
    """

    request_headers = {
        "Content-Type": "application/json",
        **(headers or {})
    }

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.post(
                target_url,
                json=mcp_json_rpc_request_dict,
                headers=request_headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            # 如果是 HTTP 错误，尝试解析错误响应
            # 安全地访问 e.response
            current_response = getattr(e, 'response', None)
            if current_response is not None:
                try:
                    error_data = current_response.json()
                    # 尝试获取更详细的错误消息
                    error_message_detail = error_data.get('error', {}).get('message', None)
                    # 如果成功获取了详细消息，可以选择记录日志，但无论如何都重新抛出原始异常 e
                    # 它已经包含了 request 和 response
                    if error_message_detail:
                        # 可选：在这里添加日志记录详细错误信息
                        # logger.error(f"MCP HTTP Error {current_response.status_code} with detail: {error_message_detail}")
                        pass 
                    raise e # 重新抛出原始异常
                except ValueError: # JSON decoding failed
                    # 如果 JSON 解析失败，也重新抛出原始异常 e
                    raise e
            else:
                # 如果原始异常没有 response (例如 ConnectError)，直接重新抛出
                raise e
