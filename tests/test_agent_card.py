import pytest

from src.translator.agent_card import def_get_mcp_gateway_agent_card, DEFAULT_AGENT_VERSION
from src.vendor.A2A.types import AgentCard, AgentCapabilities, AgentSkill, AgentProvider

def test_def_get_mcp_gateway_agent_card_default_version():
    """
    测试 def_get_mcp_gateway_agent_card 函数使用默认版本号时的行为。
    """
    host = "localhost"
    port = 8080
    expected_url = f"http://{host}:{port}/"

    agent_card = def_get_mcp_gateway_agent_card(host=host, port=port)

    assert isinstance(agent_card, AgentCard)
    assert agent_card.name == "MCP Gateway Agent"
    assert agent_card.description == "A generic A2A agent acting as a gateway to forward requests to any MCP-compliant service and receive its responses."
    assert agent_card.url == expected_url
    assert agent_card.version == DEFAULT_AGENT_VERSION # 验证默认版本
    
    assert isinstance(agent_card.capabilities, AgentCapabilities)
    assert agent_card.capabilities.streaming is False
    assert agent_card.capabilities.pushNotifications is False
    
    assert isinstance(agent_card.provider, AgentProvider)
    assert agent_card.provider.organization == "THINKER-ONLY"
    assert agent_card.provider.url == "https://github.com/THINKER-ONLY"

    assert isinstance(agent_card.skills, list)
    assert len(agent_card.skills) == 1
    skill = agent_card.skills[0]
    assert isinstance(skill, AgentSkill)
    # 我们在之前的 review 中将 agent_card.py 中的 skill id 和 name 修改了
    # 以匹配 DESIGN.md。测试应该反映这些更改。
    assert skill.id == "execute_mcp_json_rpc"
    assert skill.name == "Execute MCP JSON-RPC Method"
    assert "Executes a specified MCP JSON-RPC method" in skill.description
    assert skill.inputModes == ["data"]
    assert skill.outputModes == ["data"]
    
    assert agent_card.defaultInputModes == ["data"]
    assert agent_card.defaultOutputModes == ["data"]

def test_def_get_mcp_gateway_agent_card_custom_version():
    """
    测试 def_get_mcp_gateway_agent_card 函数使用自定义版本号时的行为。
    """
    host = "127.0.0.1"
    port = 9000
    custom_version = "1.2.3-test"
    expected_url = f"http://{host}:{port}/"

    agent_card = def_get_mcp_gateway_agent_card(host=host, port=port, version=custom_version)

    assert agent_card.url == expected_url
    assert agent_card.version == custom_version # 验证自定义版本
    # 其他字段的断言与默认版本测试类似，这里可以省略以保持简洁，
    # 除非版本变化会影响其他字段的生成逻辑（当前不会）。
    assert agent_card.name == "MCP Gateway Agent" # 确保其他部分不变 