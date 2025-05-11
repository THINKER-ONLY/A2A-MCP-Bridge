import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import json # 确保导入 json 以便在测试中使用 json.JSONDecodeError

# 从你的项目中导入被测试的函数
# 假设 src 目录在 PYTHONPATH 中，或者使用相对导入路径（如果测试文件在特定结构下）
from src.translator.mcp_client import send_mcp_request

@pytest.mark.asyncio
async def test_send_mcp_request_successful():
    """
    测试 send_mcp_request 在成功 HTTP 调用并返回有效 JSON 时的行为。
    """
    target_url = "http://fake-mcp-service.com/api"
    request_dict = {"jsonrpc": "2.0", "method": "test_method", "params": {"p1": "v1"}, "id": 1}
    expected_response_dict = {"jsonrpc": "2.0", "result": {"data": "success"}, "id": 1}
    custom_headers = {"X-Custom-Header": "TestValue"}
    timeout_val = 15.0

    # 模拟 AsyncClient 和它的 post 方法
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = expected_response_dict
    # raise_for_status 在成功时不抛出异常
    mock_response.raise_for_status = MagicMock()

    mock_async_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_async_client_instance.post.return_value = mock_response

    # 使用 patch 来替换 httpx.AsyncClient 的上下文管理器行为
    with patch("httpx.AsyncClient", return_value=mock_async_client_instance) as mock_async_client_constructor:
        actual_response = await send_mcp_request(
            target_url=target_url,
            mcp_json_rpc_request_dict=request_dict,
            headers=custom_headers,
            timeout=timeout_val
        )

    # 断言 AsyncClient 是否被正确调用
    mock_async_client_constructor.assert_called_once()
    
    # 断言 client.post 是否以预期参数被调用
    mock_async_client_instance.post.assert_called_once_with(
        target_url,
        json=request_dict,
        headers={
            "Content-Type": "application/json",
            **custom_headers
        },
        timeout=timeout_val
    )
    
    # 断言 response.raise_for_status() 被调用
    mock_response.raise_for_status.assert_called_once()
    
    # 断言 response.json() 被调用
    mock_response.json.assert_called_once()
    
    # 断言函数返回了预期的字典
    assert actual_response == expected_response_dict

@pytest.mark.asyncio
async def test_send_mcp_request_http_status_error_with_json_error_body():
    """
    测试当 HTTP 调用返回状态错误 (如 500)，且响应体包含有效的 JSON 错误信息时，
    send_mcp_request 是否能正确解析该 JSON 错误并重新抛出包含该信息的 HTTPError。
    """
    target_url = "http://fake-mcp-service.com/api_error"
    request_dict = {"jsonrpc": "2.0", "method": "cause_error", "id": 2}
    status_code = 500
    json_error_payload = {"error": {"code": -32000, "message": "Server-side MCP error", "data": {"details": "crash"}}}

    # 模拟 AsyncClient 和它的 post 方法
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.request = httpx.Request(method="POST", url=target_url) # HTTPError 需要 request 对象
    mock_response.json.return_value = json_error_payload # 模拟响应体是 JSON 错误
    
    # 模拟 raise_for_status 抛出 HTTPStatusError
    # HTTPStatusError 的 message 通常包含状态码和原因短语
    original_http_error_message = f"{status_code} Server Error: Internal Server Error for url {target_url}"
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            message=original_http_error_message, 
            request=mock_response.request, 
            response=mock_response
        )
    )

    mock_async_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_async_client_instance.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_async_client_instance):
        with pytest.raises(httpx.HTTPError) as exc_info:
            await send_mcp_request(
                target_url=target_url,
                mcp_json_rpc_request_dict=request_dict
            )
    
    # 断言抛出的异常
    assert exc_info.value.response == mock_response
    assert exc_info.value.request == mock_response.request
    # send_mcp_request 应该从 JSON body 中提取错误消息
    expected_error_message_from_json = json_error_payload["error"]["message"]
    assert str(exc_info.value) == f"HTTP {status_code}: {expected_error_message_from_json}"

    # 确保 post 和 raise_for_status 被调用
    mock_async_client_instance.post.assert_called_once()
    mock_response.raise_for_status.assert_called_once()
    # 确保 response.json() 在这种情况下也被调用了（因为要尝试解析错误体）
    mock_response.json.assert_called_once()

@pytest.mark.asyncio
async def test_send_mcp_request_http_status_error_non_json_body():
    """
    测试当 HTTP 调用返回状态错误 (如 404)，且响应体不是有效的 JSON (或不含预期错误结构) 时，
    send_mcp_request 抛出的 HTTPError 的行为。
    """
    target_url = "http://fake-mcp-service.com/not_found"
    request_dict = {"jsonrpc": "2.0", "method": "get_non_existent", "id": 3}
    status_code = 404
    non_json_response_content = b"Resource Not Found Here (HTML or plain text)"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.request = httpx.Request(method="POST", url=target_url)
    mock_response.content = non_json_response_content # 设置原始字节内容
    # 模拟 response.json() 在内容不是JSON时抛出 ValueError (或 httpx.DecodingError)
    mock_response.json.side_effect = ValueError("Could not decode JSON") 

    original_http_error_message = f"{status_code} Client Error: Not Found for url {target_url}"
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            message=original_http_error_message, 
            request=mock_response.request, 
            response=mock_response
        )
    )

    mock_async_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_async_client_instance.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_async_client_instance):
        with pytest.raises(httpx.HTTPStatusError) as exc_info: # 捕获原始或重新抛出的 HTTPStatusError
            await send_mcp_request(
                target_url=target_url,
                mcp_json_rpc_request_dict=request_dict
            )
    
    # 断言抛出的异常
    # 在这种情况下，因为 response.json() 会失败 (或者没有找到 'error' 键)，
    # send_mcp_request 中的 except ValueError: raise 会重新抛出原始的 HTTPStatusError
    # 或者如果 try 块中的 raise e (在 if e.response.json() 失败后) 执行，也是原始的 HTTPStatusError
    assert exc_info.value.response == mock_response
    assert exc_info.value.request == mock_response.request
    assert str(exc_info.value) == original_http_error_message # 消息应为原始 HTTP 错误消息

    mock_async_client_instance.post.assert_called_once()
    mock_response.raise_for_status.assert_called_once()
    mock_response.json.assert_called_once() # json() 仍然会被尝试调用

@pytest.mark.asyncio
async def test_send_mcp_request_connect_error():
    """
    测试当 httpx.AsyncClient.post 抛出 ConnectError (一种 RequestError) 时，
    send_mcp_request 是否直接向上抛出该异常。
    """
    target_url = "http://unreachable-service.com/some_path"
    request_dict = {"jsonrpc": "2.0", "method": "some_method", "id": 4}
    connect_error_message = "Connection refused"

    # 模拟 AsyncClient 和它的 post 方法抛出 ConnectError
    mock_async_client_instance = AsyncMock(spec=httpx.AsyncClient)
    # httpx.Request 对象是 ConnectError 所需的
    mock_request_obj = httpx.Request(method="POST", url=target_url)
    mock_async_client_instance.post.side_effect = httpx.ConnectError(connect_error_message, request=mock_request_obj)

    with patch("httpx.AsyncClient", return_value=mock_async_client_instance) as mock_async_client_constructor:
        with pytest.raises(httpx.ConnectError) as exc_info:
            await send_mcp_request(
                target_url=target_url,
                mcp_json_rpc_request_dict=request_dict
            )
    
    # 断言抛出的异常是预期的 ConnectError
    assert str(exc_info.value) == connect_error_message
    assert exc_info.value.request == mock_request_obj

    # 确保 AsyncClient 被构造且 post 被调用
    mock_async_client_constructor.assert_called_once()
    mock_async_client_instance.post.assert_called_once()

@pytest.mark.asyncio
async def test_send_mcp_request_response_not_json():
    """
    测试当 HTTP 调用成功 (200 OK) 但响应体不是有效 JSON 时，
    send_mcp_request 是否因 response.json() 调用而抛出 ValueError (或 JSONDecodeError)。
    """
    target_url = "http://fake-mcp-service.com/non_json_response"
    request_dict = {"jsonrpc": "2.0", "method": "get_non_json", "id": 5}
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    # 模拟 response.json() 抛出 JSONDecodeError (它是 ValueError 的子类)
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<HTML><body>Not JSON</body></HTML>", 0)
    mock_response.raise_for_status = MagicMock() # 成功时不抛出

    mock_async_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_async_client_instance.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_async_client_instance):
        with pytest.raises((ValueError, json.JSONDecodeError)) as exc_info: # httpx 可能直接抛出 JSONDecodeError
            await send_mcp_request(
                target_url=target_url,
                mcp_json_rpc_request_dict=request_dict
            )
    
    # 简单的断言，确保是 JSON 解码相关的错误
    assert "Expecting value" in str(exc_info.value)

    mock_async_client_instance.post.assert_called_once()
    mock_response.raise_for_status.assert_called_once()
    mock_response.json.assert_called_once()

# 后续可以添加更多测试用例，例如：
# - test_send_mcp_request_http_status_error_with_json_error_body
# - test_send_mcp_request_http_status_error_non_json_body
# - test_send_mcp_request_connect_error
# - test_send_mcp_request_response_not_json 