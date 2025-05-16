#!/bin/bash

# --- 配置 ---
ADAPTER_START_CMD="python -m src.translator --host 127.0.0.1 --port 8000" # 正确的 Adapter 启动命令
ADAPTER_URL="http://127.0.0.1:8000" # Adapter 基础 URL，客户端会附加 /tasks
MOCK_MCP_PORT=8001
MOCK_MCP_URL="http://127.0.0.1:${MOCK_MCP_PORT}/mcp"

# 清理函数，用于脚本退出时停止后台进程
cleanup() {
    echo "正在清理后台服务..."
    # -n 检查变量是否非空
    if [ -n "$MCP_PID" ]; then
        echo "停止模拟 MCP 服务 (PID: $MCP_PID)"
        kill $MCP_PID
    fi
    if [ -n "$ADAPTER_PID" ]; then
        echo "停止 Adapter 服务 (PID: $ADAPTER_PID)"
        kill $ADAPTER_PID
    fi
    echo "清理完成。"
}

# 设置 trap，在脚本退出（正常或异常）时调用 cleanup 函数
trap cleanup EXIT

# --- 启动服务 ---

echo "1. 启动模拟 MCP 服务 (端口: ${MOCK_MCP_PORT})..."
# 确保我们在项目根目录运行脚本，这样 python examples/... 路径才有效
python examples/MCP/service.py & # 在后台运行
MCP_PID=$! # 获取后台进程的 PID
sleep 2 # 等待服务启动

echo "2. 启动 Adapter 服务 (MCPGatewayAgent)..."
echo "   使用命令: $ADAPTER_START_CMD"
# 在后台运行 Adapter 服务
$ADAPTER_START_CMD & 
ADAPTER_PID=$!
sleep 3 # 给 Adapter 服务更多启动时间

# --- 检查服务是否启动 (可选但推荐) ---
echo "3. 检查服务是否启动..."
# 简单的检查，尝试连接端口。可以使用 nc (netcat) 或 curl
# Netcat 检查 (如果安装了)
if command -v nc &> /dev/null; then
    nc -zv 127.0.0.1 $MOCK_MCP_PORT
    nc -zv 127.0.0.1 8000 # Adapter 端口
else
    echo "'nc' (netcat) 命令未找到，跳过端口检查。"
fi

# --- 运行客户端 ---
echo "4. 运行 A2A 客户端..."
# 从项目根目录运行客户端模块，并传入正确的 URL
python -m examples.A2A.call_adapter --adapter-url "$ADAPTER_URL" --mcp-target-url "$MOCK_MCP_URL"

CLIENT_EXIT_CODE=$?

echo "客户端脚本执行完毕，退出码: $CLIENT_EXIT_CODE"

# cleanup 函数将在脚本退出时自动调用
exit $CLIENT_EXIT_CODE 