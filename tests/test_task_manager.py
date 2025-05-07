# 占位符：MCPGatewayAgentTaskManager 的单元测试

# import pytest
# from unittest.mock import AsyncMock, patch, MagicMock

# # 假设可以导入相关的类和类型
# # from translator.task_manager import MCPGatewayAgentTaskManager
# # from common.types import SendTaskRequest, Message, DataPart, TextPart # A2A types
# # from mcp import types as mcp_types # MCP types

# @pytest.mark.asyncio
# async def test_on_send_task_valid_mcp_tool_call():
#     # """测试当收到有效的A2A请求调用MCP工具时，TaskManager是否能正确处理。"""
#     # task_manager = MCPGatewayAgentTaskManager()

#     # 1. 构造一个有效的 A2A SendTaskRequest，其 DataPart 包含调用 MCP 工具的指令
#     # a2a_request_id = "test-a2a-req-1"
#     # mcp_target_url = "http://fake-mcp-service.com"
#     # mcp_tool_name = "test_tool"
#     # mcp_tool_args = {"param1": "value1"}

#     # data_payload = {
#     #     "mcp_target_url": mcp_target_url,
#     #     "mcp_method": "tools/call",
#     #     "mcp_params": {"name": mcp_tool_name, "arguments": mcp_tool_args}
#     # }
#     # a2a_task_params = {
#     #     "id": "test-task-id-1",
#     #     "message": Message(role="user", parts=[DataPart(data=data_payload)])
#     # }
#     # send_task_request = SendTaskRequest(id=a2a_request_id, params=a2a_task_params)

#     # 2. Mock `mcp_client.send_mcp_request` (或 task_manager 内部的 HTTP 调用)
#     #    使其返回一个预期的 MCP JSON-RPC 成功响应
#     # expected_mcp_result_content = [mcp_types.TextContent(type="text", text="Tool success!")]
#     # expected_mcp_call_result = mcp_types.CallToolResult(content=expected_mcp_result_content)
#     # mock_mcp_response = mcp_types.JSONRPCResponse(
#     #     jsonrpc="2.0",
#     #     id="mock-mcp-id", # MCP Gateway Agent 内部生成的 MCP 请求 ID
#     #     result=expected_mcp_call_result.model_dump()
#     # )

#     # with patch("translator.task_manager.send_mcp_request", new_callable=AsyncMock) as mock_send_mcp:
#     #     mock_send_mcp.return_value = mock_mcp_response.model_dump()

#         # 3. 调用 task_manager.on_send_task
#         # a2a_response = await task_manager.on_send_task(send_task_request)

#         # 4. 断言 A2A 响应
#         # assert a2a_response.id == a2a_request_id
#         # assert a2a_response.error is None
#         # assert a2a_response.result is not None
#         # assert a2a_response.result.status.state == "completed"
#         # assert len(a2a_response.result.artifacts) == 1
#         # output_data_part = a2a_response.result.artifacts[0].parts[0]
#         # assert isinstance(output_data_part, DataPart)
#         # # 检查 output_data_part.data 中是否正确包含了 mcp_result
#         # assert output_data_part.data["mcp_result"]["content"][0]["text"] == "Tool success!"

#         # 5. (可选) 验证 mock_send_mcp 是否以预期参数被调用
#         # mock_send_mcp.assert_called_once()
#         # called_args, called_kwargs = mock_send_mcp.call_args
#         # assert called_kwargs["target_url"] == mcp_target_url + "/messages/" # 假设默认路径
#         # mcp_req_sent = called_kwargs["mcp_json_rpc_request_dict"]
#         # assert mcp_req_sent["method"] == "tools/call"
#         # assert mcp_req_sent["params"]["name"] == mcp_tool_name
#     pass

# # 可以添加更多测试用例，例如：
# # - 测试调用 MCP 资源读取 (resources/read)
# # - 测试 MCP 服务返回错误的场景
# # - 测试网络错误或目标 MCP 服务不可达的场景
# # - 测试输入 A2A 请求无效的场景 (例如缺少 mcp_target_url) 