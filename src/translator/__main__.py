import os
import click
import logging

from dotenv import load_dotenv

from vendor.A2A.server import A2AServer
from vendor.A2A.types import AgentCard, AgentCapabilities, AgentSkill
from .task_manager import MCPGatewayAgentTaskManager
from .agent_card import def_get_mcp_gateway_agent_card

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default=os.getenv("MCP_GATEWAY_HOST", "0.0.0.0"), help="Agent 服务监听的主机地址。")
@click.option("--port", type=int, default=int(os.getenv("MCP_GATEWAY_PORT", "8080")), help="Agent 服务监听的端口。")
def main(host: str, port: int):
    """启动 MCPGatewayAgent 服务器。"""
    logger.info(f"MCPGatewayAgent 准备启动于 http://{host}:{port}")

    agent_card_instance = def_get_mcp_gateway_agent_card(host=host, port=port)

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
