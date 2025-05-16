import logging
from typing import Any, Dict, Tuple, Optional, List, Union, AsyncIterable
from uuid import uuid4
import httpx

# 从本地 vendor 目录导入 MCP 类型定义
from vendor.MCP import types as mcp_types

# 从本地 vendor 目录导入 A2A 类型定义
from src.vendor.A2A.types import (
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

from src.vendor.A2A.server.task_manager import InMemoryTaskManager
from src.vendor.A2A.server.utils import new_not_implemented_error

from src.translator.mcp_client import send_mcp_request

logger = logging.getLogger(__name__)

class MCPGatewayAgentTaskManager(InMemoryTaskManager):
    """
    管理 MCP Gateway Agent 的任务。它将 A2A 任务转换为 MCP 请求，
    发送到目标 MCP 服务，并将 MCP 响应格式化回 A2A 任务结果。
    """

    # 首先定义辅助方法
    def _format_a2a_error_response(self, request_id: Optional[str], code: int, message: str, data: Optional[Any] = None) -> JSONRPCError:
        """辅助方法，用于创建 JSONRPCError 对象。"""
        # request_id 参数在此实现中未使用，因为错误对象本身不包含请求ID。
        # 请求ID属于顶层的 JSONRPCResponse。
        return JSONRPCError(code=code, message=message, data=data)

    async def on_send_task(self, request: SendTaskRequest) -> A2AJSONRPCResponse:
        self.task_id = request.params.id
        self.session_id = request.params.sessionId
        self.last_error = None # Reset last_error for this new task

        logger.info(f"任务 [{self.task_id}] (会话 [{self.session_id}]): 已接收")

        # 步骤 1: 立即通过 upsert_task 创建或获取任务，确保它在后续操作中存在
        try:
            # InMemoryTaskManager.upsert_task 期望 TaskSendParams，并自行处理初始状态
            await self.upsert_task(request.params) 
            logger.info(f"任务 [{self.task_id}]: 已通过 upsert_task 创建/获取，初始状态为 SUBMITTED。")
        except Exception as e:
            logger.error(f"任务 [{self.task_id}]: 在 upsert_task 时发生严重错误: {e}", exc_info=True)
            json_rpc_error = self._format_a2a_error_response(
                request_id=request.id, #传递以备将来使用，但当前不由_format_a2a_error_response使用
                code=-32002, 
                message=f"Failed to initialize task in store: {str(e)}"
            )
            return A2AJSONRPCResponse(
                id=request.id,
                error=json_rpc_error.model_dump(exclude_none=True)
            )

        # 步骤 2: 解析输入
        # _parse_a2a_input 应该返回 Tuple[Optional[Dict[str, Any]], Optional[JSONRPCError]]
        # 如果解析失败，它返回 (None, JSONRPCError_object)
        # 如果成功，它返回 (parsed_params_dict, None)
        # 我们需要将这些解析后的参数存储在实例变量中，供后续方法使用
        
        parsed_params_dict, parsing_json_rpc_error = await self._parse_a2a_input(request)

        if parsing_json_rpc_error:
            logger.warning(f"任务 [{self.task_id}]: A2A 输入解析失败: {parsing_json_rpc_error.message}")
            
            # 使用现有的 _format_a2a_result_on_error
            # 它期望一个包含 "code", "message", "data" 的字典作为 error_details
            error_details_for_formatter = parsing_json_rpc_error.model_dump()

            # _format_a2a_result_on_error 返回 (TaskStatus, List[Artifact])
            failed_status, failed_artifacts = self._format_a2a_result_on_error(
                mcp_call_error_details=error_details_for_formatter,
                mcp_request_id_echo=None # No MCP request was made yet
            )
            
            # 尝试的修改: 对 history 中的 Message 进行 dump 和 re-validate
            re_validated_message_on_parse_error = None
            if request.params.message:
                message_dict_on_parse_error = request.params.message.model_dump(exclude_none=True, by_alias=True)
                try:
                    re_validated_message_on_parse_error = Message.model_validate(message_dict_on_parse_error)
                except Exception as e_val:
                    logger.error(f"任务 [{self.task_id}]: 重新验证 history message (解析错误路径) 时出错: {e_val}", exc_info=True)
                    re_validated_message_on_parse_error = request.params.message # Fallback
            
            task_history_on_parse_error = [re_validated_message_on_parse_error] if re_validated_message_on_parse_error else []

            # 创建 Task 对象
            task_result_obj = Task(
                id=self.task_id,
                sessionId=self.session_id,
                status=failed_status,
                artifacts=failed_artifacts,
                history=task_history_on_parse_error
            )
            
            await self.update_store(
                 task_id=task_result_obj.id,
                 status=task_result_obj.status,
                 artifacts=task_result_obj.artifacts if task_result_obj.artifacts else []
            )
            send_task_response_payload = SendTaskResponse(result=task_result_obj)
            return A2AJSONRPCResponse(id=request.id, result=send_task_response_payload.model_dump(exclude_none=True))
        
        # 如果解析成功，设置实例变量供后续方法（如 _execute_mcp_call, _build_mcp_request_body）使用
        self.mcp_target_url = parsed_params_dict["mcp_target_url"]
        self.mcp_request_path = parsed_params_dict["mcp_request_path"]
        self.mcp_method = parsed_params_dict["mcp_method"]
        self.mcp_params = parsed_params_dict["mcp_params"]
        self.mcp_request_id = parsed_params_dict.get("mcp_request_id") # .get 因为它是可选的

        logger.info(f"任务 [{self.task_id}]: A2A 输入成功解析。准备执行 MCP 调用。")
        status_after_parse = TaskStatus(
            state=TaskState.WORKING,
            progress=0.1,
            message=Message(role="agent", parts=[TextPart(text="A2A input parsed. Preparing MCP call.")])
        )
        await self.update_store(task_id=self.task_id, status=status_after_parse, artifacts=[])

        # 步骤 3: 执行 MCP 调用
        mcp_result, mcp_error_details = await self._execute_mcp_call()
        mcp_call_successful = mcp_result is not None and mcp_error_details is None

        if mcp_call_successful:
            logger.info(f"任务 [{self.task_id}]: MCP 调用成功。")
            status_after_mcp_success = TaskStatus(
                state=TaskState.WORKING,
                progress=0.7, 
                message=Message(role="agent", parts=[TextPart(text="MCP call successful, formatting A2A result.")])
            )
            await self.update_store(task_id=self.task_id, status=status_after_mcp_success, artifacts=[])
            successful_status, successful_artifacts = self._format_a2a_result_from_mcp_response(mcp_result, self.mcp_request_id)
            
            # 尝试的修改: 对 history 中的 Message 进行 dump 和 re-validate
            re_validated_message_on_success = None
            if request.params.message:
                message_dict_on_success = request.params.message.model_dump(exclude_none=True, by_alias=True)
                try:
                    re_validated_message_on_success = Message.model_validate(message_dict_on_success)
                except Exception as e_val:
                    logger.error(f"任务 [{self.task_id}]: 重新验证 history message (成功路径) 时出错: {e_val}", exc_info=True)
                    re_validated_message_on_success = request.params.message # Fallback

            task_history_on_success = [re_validated_message_on_success] if re_validated_message_on_success else []
            
            task_result_obj = Task(
                id=self.task_id,
                sessionId=self.session_id,
                status=successful_status,
                artifacts=successful_artifacts,
                history=task_history_on_success
            )
        else:
            logger.error(f"任务 [{self.task_id}]: MCP 调用失败或返回错误。详细信息: {mcp_error_details}")
            error_code = "mcp_call_failed"
            error_message = str(mcp_error_details)
            error_data = None
            if isinstance(mcp_error_details, dict):
                error_message = mcp_error_details.get("message", error_message)
                error_code = str(mcp_error_details.get("code", error_code))
                error_data = mcp_error_details.get("data")
            
            status_on_mcp_fail, artifacts_on_mcp_fail = self._format_a2a_result_on_error(
                 mcp_call_error_details=mcp_error_details if isinstance(mcp_error_details, dict) else {"code": error_code, "message": error_message, "data": error_data},
                 mcp_request_id_echo=self.mcp_request_id
            )
            await self.update_store(task_id=self.task_id, status=status_on_mcp_fail, artifacts=artifacts_on_mcp_fail)
            task_result_obj = await self.get_task(self.task_id)
            if task_result_obj is None: # Should not happen if update_store succeeded
                # 尝试的修改: 对 history 中的 Message 进行 dump 和 re-validate (错误路径中的 fallback)
                re_validated_message_on_mcp_fail_fallback = None
                if request.params.message: # request 可能不存在于此更深层的作用域，假设它仍然可访问或使用类属性
                    message_dict_on_mcp_fail_fallback = request.params.message.model_dump(exclude_none=True, by_alias=True)
                    try:
                        re_validated_message_on_mcp_fail_fallback = Message.model_validate(message_dict_on_mcp_fail_fallback)
                    except Exception as e_val:
                        logger.error(f"任务 [{self.task_id}]: 重新验证 history message (MCP失败回退路径) 时出错: {e_val}", exc_info=True)
                        re_validated_message_on_mcp_fail_fallback = request.params.message # Fallback
                
                task_history_on_mcp_fail_fallback = [re_validated_message_on_mcp_fail_fallback] if re_validated_message_on_mcp_fail_fallback else []

                task_result_obj = Task(id=self.task_id, sessionId=self.session_id, status=status_on_mcp_fail, artifacts=artifacts_on_mcp_fail, history=task_history_on_mcp_fail_fallback)

        if task_result_obj is None: # Fallback
            logger.error(f"任务 [{self.task_id}]: 未能格式化有效的 Task 对象。使用通用错误。")
            # 为了安全，如果进入此分支，history 保持为空。
            
            # 修正：下面的调用是错误的，_format_a2a_result_on_error 期望字典
            # general_failed_status, general_failed_artifacts = self._format_a2a_result_on_error(
            #     {"code": "internal_formatting_error", "message": "Internal error: Failed to format A2A result."} # 示例错误字典
            # )
            # task_result_obj = Task(
            #     id=self.task_id, 
            #     sessionId=self.session_id, 
            #     status=general_failed_status, 
            #     artifacts=general_failed_artifacts, 
            #     history=[] # 在这种通用错误情况下，history 为空
            # )

            # 保持原有逻辑，仅在task_result_obj已存在但history可能需要处理时考虑
            # 但如果 task_result_obj 本身是 None，则创建它，此时 history 保持为空
            general_failed_status = TaskStatus(state=TaskState.FAILED, message=Message(role="agent", parts=[TextPart(text="Internal error: Failed to format A2A result.")]))
            task_result_obj = Task(
                id=self.task_id,
                sessionId=self.session_id,
                status=general_failed_status,
                artifacts=[], # No specific artifacts for this generic error
                history=[] # Keep history empty for this very generic fallback
            )
        
        # 步骤 4: 更新存储并返回最终响应
        final_status_to_log = task_result_obj.status.state.value if task_result_obj.status else TaskState.UNKNOWN.value
        logger.info(f"任务 [{self.task_id}]: 最终任务状态为 {final_status_to_log}。准备更新存储并发送响应。")
        await self.update_store(
            task_id=task_result_obj.id, 
            status=task_result_obj.status, 
            artifacts=task_result_obj.artifacts if task_result_obj.artifacts else []
        )
        
        # 构建 SendTaskResponse 实例，其 id 为原始请求的 id，result 为 Task 对象
        send_task_response_obj = SendTaskResponse(
            id=request.id, # 使用原始请求的 ID
            result=task_result_obj # result 是 Task 实例
        )

        # 使用 SendTaskResponse 实例自身的 model_dump_json 用于调试日志
        logger.debug(f"任务 [{self.task_id}]: 最终响应对象 (SendTaskResponse): {send_task_response_obj.model_dump_json(exclude_none=True, indent=2)}")
        
        #直接返回 SendTaskResponse 实例
        return send_task_response_obj

    async def _parse_a2a_input(self, request: SendTaskRequest) -> Tuple[Optional[Dict[str, Any]], Optional[JSONRPCError]]:
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
            if not request.params.message.parts or len(request.params.message.parts) == 0:
                return None, JSONRPCError(
                    code=-32602,
                    message="消息必须包含至少一个部分",
                    data={"detail": "Message must contain at least one part"}
                )

            first_part = request.params.message.parts[0]
            
            # 修改检查逻辑：
            # 1. 检查 'type' 属性是否存在且等于 'data'
            # 2. 检查 'data' 属性是否存在
            part_type = getattr(first_part, 'type', None)
            # first_part 可能没有 'data' 属性，即使 type 是 'data' (例如，如果它是一个不完整的模型)
            # 所以我们同时检查 getattr(first_part, 'data', None) is not None
            # 并且，即使 'data' 属性存在，它也必须是一个字典
            first_part_data_attr = getattr(first_part, 'data', None)

            if not (part_type == "data" and first_part_data_attr is not None and isinstance(first_part_data_attr, dict)):
                return None, JSONRPCError(
                    code=-32602,
                    message="第一个部分必须是有效的 DataPart (type='data' 且其 'data' 字段为字典)",
                    data={"detail": f"First part type was '{part_type}', data attribute present: {first_part_data_attr is not None}, data attribute is dict: {isinstance(first_part_data_attr, dict)}"}
                )
            
            # 现在 data_payload 是 first_part.data，并且我们知道它是一个字典
            data_payload: Dict[str, Any] = first_part_data_attr
            
            required_fields = ["mcp_target_url", "mcp_method", "mcp_params"]
            for field in required_fields:
                if field not in data_payload: # 检查 data_payload
                    return None, JSONRPCError(
                        code=-32602,
                        message=f"缺少必需字段: {field}",
                        data={"detail": f"Missing required field: {field}"}
                    )
                
            if not isinstance(data_payload["mcp_target_url"], str):
                return None, JSONRPCError(
                    code=-32602,
                    message="mcp_target_url 必须是字符串",
                    data={"detail": "mcp_target_url must be a string"}
                )
            
            if not isinstance(data_payload["mcp_method"], str):
                return None, JSONRPCError(
                    code=-32602,
                    message="mcp_method 必须是字符串",
                    data={"detail": "mcp_method must be a string"}
                )
            
            if not isinstance(data_payload["mcp_params"], dict):
                return None, JSONRPCError(
                    code=-32602,
                    message="mcp_params 必须是字典",
                    data={"detail": "mcp_params must be a dictionary"}
                )
            
            # 检查可选字段的类型 (如果存在)
            if "mcp_request_path" in data_payload and not isinstance(data_payload["mcp_request_path"], str):
                return None, JSONRPCError(
                    code=-32602,
                    message="如果提供，mcp_request_path 必须是字符串",
                    data={"detail": "mcp_request_path must be a string if provided"}
                )

            if "mcp_request_id" in data_payload and not isinstance(data_payload["mcp_request_id"], (str, int)):
                 return None, JSONRPCError(
                    code=-32602,
                    message="如果提供，mcp_request_id 必须是字符串或整数",
                    data={"detail": "mcp_request_id must be a string or integer if provided"}
                )
            
            params = {
                "mcp_target_url": data_payload["mcp_target_url"],
                "mcp_method": data_payload["mcp_method"],
                "mcp_params": data_payload["mcp_params"],
                "mcp_request_path": data_payload.get("mcp_request_path", ""),
                "mcp_request_id": data_payload.get("mcp_request_id")
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

    async def _execute_mcp_call(self) -> Tuple[Optional[Dict[str, Any]], Optional[JSONRPCError]]:
        """
        使用 mcp_client 发送 MCP 请求并处理 HTTP/网络错误。
        返回 MCP 响应的 result 部分 (字典) 或一个用于 A2A 的 JSONRPCError。
        """
        # 这些 self. 属性应该由 on_send_task 在调用此方法前通过 _parse_a2a_input 的结果设置
        current_mcp_target_url = self.mcp_target_url 
        current_mcp_request_path = self.mcp_request_path

        full_mcp_url = current_mcp_target_url 
        if current_mcp_request_path: # 仅当 current_mcp_request_path 非空时才进行拼接
            processed_target_url = current_mcp_target_url.rstrip('/')
            processed_request_path = current_mcp_request_path
            if not processed_request_path.startswith('/'):
                processed_request_path = '/' + processed_request_path
            full_mcp_url = f"{processed_target_url}{processed_request_path}"
        
        # mcp_request_body 也应从 self. 属性或参数获取，这里假设 on_send_task 会准备好 self.mcp_request_body
        # 或者 _build_mcp_request_body 使用 self. 属性
        # 为了与现有代码兼容，我们假设 _build_mcp_request_body 使用 self.mcp_method, self.mcp_params, self.mcp_request_id
        # 而这些 self. 属性是在 on_send_task 中，在调用 _execute_mcp_call 之前，从 _parse_a2a_input 的结果中设置的。
        # 注意: 原代码中 _build_mcp_request_body 接收参数，_execute_mcp_call 中并没有直接使用 self.mcp_request_body
        # 这里我们需要确保 mcp_request_body 被正确构建并传递给 send_mcp_request
        # 假设 on_send_task 的逻辑是: 
        #   parsed_data = await self._parse_a2a_input(...)
        #   self.mcp_target_url = parsed_data["mcp_target_url"]
        #   ...
        #   self.mcp_request_body_dict = self._build_mcp_request_body(self.mcp_method, self.mcp_params, self.mcp_request_id)
        #   result, error = await self._execute_mcp_call() <-- _execute_mcp_call 现在可以不接收参数，直接用 self. 属性
        # 或者，保持 _execute_mcp_call 接收参数，但 on_send_task 要正确传递它们。
        # 为了最小化改动并与您提供的 _execute_mcp_call 签名一致，它不接收这些参数。
        # 因此，它必须依赖于 self.mcp_method, self.mcp_params, self.mcp_request_id 被设置。
        
        # 构建请求体，这里假设 _build_mcp_request_body 使用实例变量
        # (这与您当前代码中 _build_mcp_request_body 的签名不同，它接收参数)
        # 为了匹配 _execute_mcp_call 的逻辑，我们需要在 on_send_task 中先调用 _build_mcp_request_body
        # 并将其结果 (一个字典) 传递给 _execute_mcp_call，或者让 _execute_mcp_call 内部调用它。
        
        # 我们将遵循 _execute_mcp_call 内部构建 request_body 的模式，假设相关 self 属性已设置
        mcp_http_request_body = self._build_mcp_request_body(
            method=self.mcp_method, 
            params=self.mcp_params, 
            request_id=self.mcp_request_id
        )

        try:
            raw_response_dict = await send_mcp_request(full_mcp_url, mcp_http_request_body)

            # 尝试将响应解析为 MCP JSON-RPC 错误或成功响应
            # MCP 服务对于 JSON-RPC 级别的错误通常也返回 HTTP 200 OK
            if "error" in raw_response_dict and "id" in raw_response_dict:
                try:
                    mcp_error_obj = mcp_types.JSONRPCError.model_validate(raw_response_dict)
                    error_dict_for_a2a = {
                        "code": mcp_error_obj.error.code,
                        "message": mcp_error_obj.error.message,
                        "data": mcp_error_obj.error.data
                    }
                    return None, JSONRPCError.model_validate(error_dict_for_a2a)
                except Exception as val_err: 
                    logger.warning(f"MCP响应看似错误, 但mcp_types.JSONRPCError验证失败: {val_err}. 回退到原始解析。URL: {full_mcp_url}")
                    error_payload = raw_response_dict.get("error", {})
                    fallback_error_dict = {
                        "code": error_payload.get("code", mcp_types.INTERNAL_ERROR),
                        "message": error_payload.get("message", "未知的MCP错误结构"),
                        "data": error_payload.get("data")
                    }
                    return None, JSONRPCError.model_validate(fallback_error_dict)
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
            status_code = None
            # 安全地访问 e.response 和 e.response.status_code
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
            
            logger.error(f"MCP HTTPError (状态码: {status_code if status_code else 'N/A'}) 调用 {full_mcp_url}: {error_message}", exc_info=True)
            http_error_dict = {
                "code": status_code or mcp_types.INTERNAL_ERROR,
                "message": error_message, 
                "data": {"details": f"MCP调用期间发生HTTP/网络层错误 (URL: {full_mcp_url})"}
            }
            return None, JSONRPCError.model_validate(http_error_dict)
        except ValueError as e: 
            logger.error(f"MCP ValueError (JSON解码) 调用 {full_mcp_url}: {str(e)}", exc_info=True)
            value_error_dict = {
                "code": mcp_types.PARSE_ERROR,
                "message": "MCP服务返回非JSON响应或格式错误的JSON。",
                "data": {"details": str(e), "url": full_mcp_url}
            }
            return None, JSONRPCError.model_validate(value_error_dict)
        except Exception as e: 
            logger.error(f"MCP调用期间发生意外错误 {full_mcp_url}: {str(e)}", exc_info=True)
            unexpected_error_dict = {
                "code": mcp_types.INTERNAL_ERROR,
                "message": "与MCP服务通信时发生意外错误。",
                "data": {"details": str(e), "url": full_mcp_url}
            }
            return None, JSONRPCError.model_validate(unexpected_error_dict)

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
            parts=[TextPart(text=status_message_text)]
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

    
    