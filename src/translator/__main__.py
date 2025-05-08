import os
import click
import logging

from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill
from .task_manager import MCPGatewayAgentTaskManager

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default=os.getenv("MCP_GATEWAY_HOST", "0.0.0.0"), help="Agent 服务监听的主机地址。")
@click.option("--port", type=int, default=int(os.getenv("MCP_GATEWAY_PORT", "8080")), help="Agent 服务监听的端口。")
def main(host: str, port: int):
    """启动 MCPGatewayAgent 服务器。"""
    logger.info(f"MCPGatewayAgent 准备启动于 http://{host}:{port}")

    capabilities = AgentCapabilities(streaming=False, pushNotifications=False)

    skill = AgentSkill(
        id="execute_mcp_command",
        name="Execute MCP Command",
        description="在目标 MCP 服务上使用给定参数执行指定的 MCP JSON-RPC 方法。命令详细信息在输入的 DataPart 中提供。",
        inputModes=["data"],
        outputModes=["data"],
    )

    agent_card_instance = AgentCard(
        name="MCP Gateway Agent",
        description="一个通用的 A2A 代理，充当网关，用于将请求转发到任何符合 MCP 规范的服务并接收其响应。",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        capabilities=capabilities,
        skills=[skill],
        defaultInputModes=["data"],
        defaultOutputModes=["data"],
    )

    task_manager_instance = MCPGatewayAgentTaskManager()

    server = A2AServer(
        agent_card=agent_card_instance,
        task_manager=task_manager_instance,
        host=host,
        port=port,
    )

    logger.info(f"启动服务器于 http://{host}:{port}")
    logger.info(f"A2A Agent Card URL: http://{host}:{port}/")
    try:
        server.start()
    except Exception as e:
        logger.error(f"服务器启动失败: {e}", exc_info=True)

if __name__ == "__main__":
    main()
