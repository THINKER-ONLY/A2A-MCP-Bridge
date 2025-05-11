import logging
from typing import Any, Dict, Tuple, Optional, List, Union, AsyncIterable
from uuid import uuid4
import httpx

# 从本地 vendor 目录导入 MCP 类型定义
from vendor.MCP import types as mcp_types

# 从本地 vendor 目录导入 A2A 类型定义
from vendor.A2A.types import (
    Artifact,
    DataPart,
    JSONRPCError,
    Message,
    SendTaskRequest,
    SendTaskResponse,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    JSONRPCResponse as A2AJSONRPCResponse 
)

from vendor.A2A.server.task_manager import InMemoryTaskManager
from vendor.A2A.server.utils import new_not_implemented_error

from .mcp_client import send_mcp_request

logger = logging.getLogger(__name__)

class MCPGatewayAgentTaskManager(InMemoryTaskManager):
    """
    管理 MCP Gateway Agent 的任务。它将 A2A 任务转换为 MCP 请求，
    发送到目标 MCP 服务，并将 MCP 响应格式化回 A2A 任务结果。
    """

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        task_id = request.params.id
        session_id = request.params.sessionId
        incoming_message = request.params.message

        logger.info(f"任务 [{task_id}] (会话 [{session_id}]): 已接收。正在处理...")
        # ---------- 工作流步骤 ----------

        # 步骤 1: 解析并验证 A2A 输入
        # 目标: 从 incoming_message.parts[0].data 中提取 MCP 调用参数
        # 输出: mcp_调用参数字典 (mcp_call_params_dict) 或一个 A2A 错误对象 (error_for_a2a)
        parsed_input, extraction_error = self._parse_a2a_input(incoming_message)
        
        if extraction_error:
            logger.error(f"任务 [{task_id}]: 解析 A2A 输入失败。错误: {extraction_error.message}")
            failed_status = TaskStatus(
                state = TaskState.FAILED,
                message = Message(
                    role = "agent",
                    parts=[DataPart(data={"error_summary": "无效的 A2A 任务输入。", "detail": extraction_error.model_dump()})],
                )
            )
            updated_task = await self.update_store(task_id, session_id, failed_status, [], incoming_message)
            return SendTaskResponse(result=updated_task, error=extraction_error)
        
        mcp_target_url = parsed_input["mcp_target_url"]
        mcp_request_path = parsed_input["mcp_request_path"]
        mcp_method_to_call = parsed_input["mcp_method"]
        mcp_params_for_call = parsed_input["mcp_params"]
        original_mcp_request_id = parsed_input.get("mcp_request_id")

        # 步骤 2: 构建 MCP JSON-RPC 请求体  
        # 目标: 构造用于 MCP HTTP POST 请求的字典负载。
        # 输出: mcp_请求体字典 (mcp_request_body_dict)
        mcp_request_body = self._build_mcp_request_body(
            method=mcp_method_to_call,
            params=mcp_params_for_call,
            request_id=original_mcp_request_id
        )
        mcp_request_id_sent = mcp_request_body.get("id")

        # 步骤 3 & 4: 执行 MCP 调用 (发送请求和接收响应)
        # 目标: 使用 mcp_client.send_mcp_request 与目标 MCP 服务通信。
        # 输出: mcp_响应负载字典 (mcp_response_payload_dict) 或一个 A2A 错误对象 (error_for_a2a)
        logger.info(f"任务 [{task_id}]: 准备发送 MCP 请求 '{mcp_method_to_call}' 到 {mcp_target_url}{mcp_request_path}")
        mcp_response_payload, mcp_call_error = await self._execute_mcp_call(
            target_base_url = mcp_target_url,
            request_path = mcp_request_path,
            mcp_request_body = mcp_request_body
        )

        if mcp_call_error:
            logger.error(f"任务 [{task_id}]: MCP 调用失败。错误: {mcp_call_error.message}")
            failed_status, artifacts_with_error = self._format_a2a_result_on_error(
                mcp_call_error_details=mcp_call_error.model_dump(),
                mcp_request_id_echo=mcp_request_id_sent
            )
            updated_task = await self.update_store(task_id, session_id, failed_status, artifacts_with_error, incoming_message)
            return SendTaskResponse(result=updated_task, error=mcp_call_error)
        
        # 步骤 5: 从 MCP 响应格式化 A2A 任务结果
        # 目标: 将成功的 (或 MCP 层面错误的) mcp_response_payload 转换为 A2A TaskStatus 和 Artifacts。
        # 输出: final_task_status, list_of_artifacts
        logger.info(f"任务 [{task_id}]: MCP 调用成功 (或 MCP 返回了结构化错误)。正在格式化 A2A 结果。")
        final_task_status, final_artifacts = self._format_a2a_result_from_mcp_response(
            mcp_response_data=mcp_response_payload, # 这个字典包含来自 MCP 的 "result" 或 "error"
            mcp_request_id_echo=mcp_request_id_sent
        )
        
        # 步骤 6: 更新任务存储并返回 A2A 响应
        logger.info(f"任务 [{task_id}]: 最终 A2A 状态: {final_task_status.state}。正在更新存储。")
        updated_task = await self.update_store(
            task_id,
            session_id,
            final_task_status,
            final_artifacts,
            incoming_message
        )
        return SendTaskResponse(result=updated_task)

    def _parse_a2a_input(self, message: Message) -> Tuple[Optional[Dict[str, Any]], Optional[JSONRPCError]]:
        """
        解析传入的 A2A Message 以提取 MCP 调用参数。
        如果解析失败，返回参数字典或一个 JSONRPCError。
        DataPart.data 中期望的字段:
            - "mcp_target_url": str (必需)
            - "mcp_method": str (必需)
            - "mcp_params": dict (必需)
            - "mcp_request_path": str (可选, 默认为 "/messages/")
            - "mcp_request_id": str | int (可选)
        """
        try:
            if not message.parts or len(message.parts) == 0:
                return None, JSONRPCError(
                    code=-32602,
                    message="消息必须包含至少一个部分",
                    data={"detail": "Message must contain at least one part"}
                )

            first_part = message.parts[0]
            if not isinstance(first_part, DataPart):
                return None, JSONRPCError(
                    code=-32602,
                    message="第一个部分必须是 DataPart 类型",
                    data={"detail": "First part must be a DataPart"}
                )
            
            data = first_part.data
            required_fields = ["mcp_target_url", "mcp_method", "mcp_params"]
            for field in required_fields:
                if field not in data:
                    return None, JSONRPCError(
                        code=-32602,
                        message=f"缺少必需字段: {field}",
                        data={"detail": f"Missing required field: {field}"}
                    )
                
            if not isinstance(data["mcp_target_url"], str):
                return None, JSONRPCError(
                    code=-32602,
                    message="mcp_target_url 必须是字符串",
                    data={"detail": "mcp_target_url must be a string"}
                )
            
            if not isinstance(data["mcp_method"], str):
                return None, JSONRPCError(
                    code=-32602,
                    message="mcp_method 必须是字符串",
                    data={"detail": "mcp_method must be a string"}
                )
            
            if not isinstance(data["mcp_params"], dict):
                return None, JSONRPCError(
                    code=-32602,
                    message="mcp_params 必须是字典",
                    data={"detail": "mcp_params must be a dictionary"}
                )
            
            params = {
                "mcp_target_url": data["mcp_target_url"],
                "mcp_method": data["mcp_method"],
                "mcp_params": data["mcp_params"],
                "mcp_request_path": data.get("mcp_request_path", "/messages/"),
                "mcp_request_id": data.get("mcp_request_id")
            }
            return params, None

        except Exception as e:
            logger.error(f"解析 A2A 输入时发生错误: {str(e)}", exc_info=True)
            return None, JSONRPCError(
                code=-32603,
                message="解析 A2A 输入时发生内部错误",
                data={"detail": str(e)}
            )
            

    def _build_mcp_request_body(self, method: str, params: Dict[str, Any], request_id: Optional[str | int]) -> Dict[str, Any]:
        """
        构造标准的 JSON-RPC 2.0 请求体 (作为字典)，使用 mcp_types。
        """
        if request_id is None:
            request_id = str(uuid4())
        
        mcp_req_obj = mcp_types.JSONRPCRequest(
            jsonrpc="2.0",
            id=request_id,
            method=method,
            params=params
        )
        # exclude_none=True 确保可选字段为 None 时不包含在输出字典中
        return mcp_req_obj.model_dump(exclude_none=True)

    async def _execute_mcp_call(self, target_base_url: str, request_path: str, mcp_request_body: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[JSONRPCError]]:
        """
        使用 mcp_client 发送 MCP 请求并处理 HTTP/网络错误。
        返回 MCP 响应的 result 部分 (字典) 或一个用于 A2A 的 JSONRPCError。
        """
        # 确保 target_base_url 总是以单个斜杠结尾，然后附加 request_path
        # 这有助于避免双斜杠或缺少斜杠的问题
        if not target_base_url.endswith("/"):
            target_base_url += "/"
        
        # request_path 通常以 / 开头，但也可能不是，所以 lstrip 一下以防万一
        # 如果 request_path 为空或 "/"，urljoin 的行为可能更可预测，但这里简化处理
        full_mcp_url = target_base_url + request_path.lstrip("/")

        try:
            raw_response_dict = await send_mcp_request(full_mcp_url, mcp_request_body)

            # 尝试将响应解析为 MCP JSON-RPC 错误或成功响应
            # MCP 服务对于 JSON-RPC 级别的错误通常也返回 HTTP 200 OK
            if "error" in raw_response_dict and "id" in raw_response_dict:
                try:
                    mcp_error_obj = mcp_types.JSONRPCError.model_validate(raw_response_dict)
                    # 将 MCP SDK 的 ErrorData 转换为 A2A JSONRPCError
                    return None, JSONRPCError(
                        code=mcp_error_obj.error.code,
                        message=mcp_error_obj.error.message,
                        data=mcp_error_obj.error.data
                    )
                except Exception as val_err: # Pydantic validation error
                    logger.warning(f"MCP响应看似错误, 但mcp_types.JSONRPCError验证失败: {val_err}. 回退到原始解析。URL: {full_mcp_url}")
                    error_payload = raw_response_dict.get("error", {})
                    return None, JSONRPCError(
                        code=error_payload.get("code", mcp_types.INTERNAL_ERROR),
                        message=error_payload.get("message", "未知的MCP错误结构"),
                        data=error_payload.get("data")
                    )
            elif "result" in raw_response_dict and "id" in raw_response_dict:
                try:
                    mcp_success_obj = mcp_types.JSONRPCResponse.model_validate(raw_response_dict)
                    # 返回 MCP 响应中的 'result' 部分，它本身应该是一个字典
                    if isinstance(mcp_success_obj.result, dict):
                        return mcp_success_obj.result, None
                    else:
                        # 如果 result 不是字典，可能需要根据具体业务调整
                        # 例如，如果允许其他类型，或将其包装在字典中
                        logger.warning(f"MCP响应的result字段不是预期的字典类型。URL: {full_mcp_url}, Result: {mcp_success_obj.result}")
                        # 作为一种容错，如果result不是None，但也不是字典，我们将其作为data传递，但这可能需要进一步处理
                        return {"non_dict_result": mcp_success_obj.result} if mcp_success_obj.result is not None else {}, None
                except Exception as val_err: # Pydantic validation error
                    logger.warning(f"MCP成功响应验证失败: {val_err}. 直接返回原始字典。URL: {full_mcp_url}")
                    # 如果验证失败，但包含 result，仍返回原始字典（这部分是传给 _format_a2a_result_from_mcp_response）
                    return raw_response_dict, None 
            else:
                # 响应既不完全符合JSONRPCError也不完全符合JSONRPCResponse的结构，但HTTP成功
                logger.warning(f"MCP响应结构未知，但HTTP调用成功。URL: {full_mcp_url}, Response: {raw_response_dict}")
                # 仍然将其视为成功传递给格式化函数，让它决定如何处理
                return raw_response_dict, None

        except httpx.HTTPError as e:
            error_message = str(e)
            status_code = e.response.status_code if e.response else None
            logger.error(f"MCP HTTPError (状态码: {status_code}) 调用 {full_mcp_url}: {error_message}", exc_info=True)
            return None, JSONRPCError(
                code=status_code or mcp_types.INTERNAL_ERROR, # 使用HTTP状态码或通用内部错误码
                message=error_message, 
                data={"details": f"MCP调用期间发生HTTP/网络层错误 (URL: {full_mcp_url})"}
            )
        except ValueError as e: # JSON decoding error from mcp_client
            logger.error(f"MCP ValueError (JSON解码) 调用 {full_mcp_url}: {str(e)}", exc_info=True)
            return None, JSONRPCError(
                code=mcp_types.PARSE_ERROR,
                message="MCP服务返回非JSON响应或格式错误的JSON。",
                data={"details": str(e), "url": full_mcp_url}
            )
        except Exception as e: # Catch-all for other unexpected errors
            logger.error(f"MCP调用期间发生意外错误 {full_mcp_url}: {str(e)}", exc_info=True)
            return None, JSONRPCError(
                code=mcp_types.INTERNAL_ERROR,
                message="与MCP服务通信时发生意外错误。",
                data={"details": str(e), "url": full_mcp_url}
            )

    def _format_a2a_result_from_mcp_response(self, mcp_response_data: Dict[str, Any], mcp_request_id_echo: Optional[str | int]) -> Tuple[TaskStatus, List[Artifact]]:
        """
        将 MCP 服务的响应数据 (通常是JSON-RPC的result字段内容, 或包含error的完整JSON-RPC结构) 
        格式化为 A2A TaskStatus 和 Artifacts。
        """
        actual_data_part = DataPart(
            data=mcp_response_data,
            metadata={"mcp_request_id_echo": str(mcp_request_id_echo) if mcp_request_id_echo is not None else None}
        )

        result_artifact = Artifact(
            name="MCP Service Response",
            description="Payload received from the MCP service.",
            parts=[actual_data_part]
        )

        status_message_text = "MCP request processed successfully."
        if "error" in mcp_response_data:
            mcp_error_obj = mcp_response_data.get("error", {})
            status_message_text = f"MCP service returned an error: {mcp_error_obj.get('message', 'Unknown MCP error')}"

        status_message = Message(
            role="agent",
            ports=[TextPart(text=status_message_text)]
        )

        final_task_status = TaskStatus(
            state=TaskState.COMPLETED,
            message=status_message    
        )

        return final_task_status, [result_artifact]

    def _format_a2a_result_on_error(self, mcp_call_error_details: Dict[str, Any], mcp_request_id_echo: Optional[str | int]) -> Tuple[TaskStatus, List[Artifact]]:
        """
        当发生直接通信错误 (不是 MCP 返回的错误) 时，格式化 A2A TaskStatus 和 Artifacts。
        mcp_call_error_details 是 JSONRPCError.model_dump() 的结果。
        """
        error_code = mcp_call_error_details.get("code", mcp_types.INTERNAL_ERROR) # 修正：从 "code" 键获取
        error_message_str = mcp_call_error_details.get("message", "Unknown communication error with MCP service")
        error_data_payload = mcp_call_error_details.get("data") 

        error_detail_data_for_part = {
            "source_error": mcp_call_error_details,
            "mcp_request_id_echo": str(mcp_request_id_echo) if mcp_request_id_echo is not None else None
        }
        
        error_data_part = DataPart(data=error_detail_data_for_part)
        
        error_artifact = Artifact(
            name="MCP Call Communication Error",
            description=f"Failed to communicate with MCP service: {error_message_str}",
            parts=[error_data_part]
        )

        status_message = Message(
            role="agent",
            parts=[TextPart(text=f"Failed to execute MCP call: {error_message_str}")]
        )

        final_task_status = TaskStatus(
            state=TaskState.FAILED,
            message=status_message
        )
        
        return final_task_status, [error_artifact]

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> Union[AsyncIterable[SendTaskStreamingResponse], A2AJSONRPCResponse]:
        """
        此 Agent 不支持流式任务订阅。
        """
        logger.warning(
            f"任务 [{request.params.id}] (会话 [{request.params.sessionId}]): "
            f"尝试订阅流式任务，但此 Agent 不支持。"
        )
        return new_not_implemented_error(request.id)

    
    