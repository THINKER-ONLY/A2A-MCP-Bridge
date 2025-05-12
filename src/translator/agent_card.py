from src.vendor.A2A.types import AgentCard, AgentCapabilities, AgentSkill, AgentProvider

DEFAULT_AGENT_VERSION = "0.1.0"

def def_get_mcp_gateway_agent_card(host: str, port: int, version: str = DEFAULT_AGENT_VERSION) -> AgentCard:
    """
    创建并返回 MCP Gateway Agent 的 AgentCard。
    Args:
        host: Agent 服务监听的主机名或 IP 地址。
        port: Agent 服务监听的端口号。
        version: Agent 的版本号。

    Returns:
        AgentCard: 配置好的 AgentCard 实例。
    """

    agent_url = f"http://{host}:{port}/"

    capabilities = AgentCapabilities(
        streaming=False,
        pushNotifications=False
    )

    execute_mcp_skill = AgentSkill(
        id="execute_mcp_json_rpc",
        name="Execute MCP JSON-RPC Method",
        description="Executes a specified MCP JSON-RPC method on a target MCP service with given parameters. "
                    "Command details (target_url, method, params, etc.) are provided in the input DataPart.",
        inputModes=["data"],
        outputModes=["data"]
    )

    provider_info = AgentProvider(
        organization="THINKER-ONLY",
        url="https://github.com/THINKER-ONLY"
    )

    agent_card_instance = AgentCard(
        name="MCP Gateway Agent",
        description="A generic A2A agent acting as a gateway to forward requests to any MCP-compliant service and receive its responses.",
        url=agent_url,
        version=version,
        capabilities=capabilities,
        skills=[execute_mcp_skill],
        provider=provider_info,
        defaultInputModes=["data"],
        defaultOutputModes=["data"],
    )

    return agent_card_instance