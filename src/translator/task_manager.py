import logging
from typing import Any, Dict, Tuple, Optional, List

from common.server.task_manager import InMemoryTaskManager, TaskManagerError
from common.types import (
    Artifact,
    DataPart,
    JSONRPCError,
    Message,
    SendTaskRequest,
    SendTaskResponse,
    Task,
    TaskState,
    TaskStatus,
)

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
            mcp_response_payload=mcp_response_payload, # 这个字典包含来自 MCP 的 "result" 或 "error"
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
        pass

    def _build_mcp_request_body(self, method: str, params: Dict[str, Any], request_id: Optional[str | int]) -> Dict[str, Any]:
        """
        构造标准的 JSON-RPC 2.0 请求体 (作为字典)。
        """
        pass

    async def _execute_mcp_call(self, target_base_url: str, request_path: str, mcp_request_body: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[JSONRPCError]]:
        """
        使用 mcp_client 发送 MCP 请求并处理 HTTP/网络错误。
        返回 MCP 响应负载 (字典) 或一个用于 A2A 的 JSONRPCError。
        """
        pass

    def _format_a2a_result_from_mcp_response(self, mcp_response_payload: Dict[str, Any], mcp_request_id_echo: Optional[str | int]) -> Tuple[TaskStatus, List[Artifact]]:
        """
        将 MCP JSON-RPC 响应 (其本身可能是成功或 MCP 错误对象) 格式化为 A2A TaskStatus 和 Artifacts。
        输出 DataPart 结构请参考 DESIGN.md。
        """   
        pass

    def _format_a2a_result_on_error(self, mcp_call_error_details: Dict[str, Any], mcp_request_id_echo: Optional[str | int]) -> Tuple[TaskStatus, List[Artifact]]:
        """
        当发生直接通信错误 (不是 MCP 返回的错误) 时，格式化 A2A TaskStatus 和 Artifacts。
        """
        pass

    
    