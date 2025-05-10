import httpx
from typing import Dict, Any, Optional
from mcp import types as mcp_types

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

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                target_url,
                json=mcp_json_rpc_request_dict,
                headers=request_headers,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            # 如果是 HTTP 错误，尝试解析错误响应
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('error', {}).get('message', str(e))
                    raise httpx.HTTPError(
                        f"HTTP {e.response.status_code}: {error_message}",
                        request=e.request,
                        response=e.response
                    )
                except ValueError:
                    raise
            raise
