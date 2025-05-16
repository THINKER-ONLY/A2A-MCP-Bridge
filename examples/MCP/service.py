#!/usr/bin/env python
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json

app = FastAPI(
    title="模拟 MCP 服务",
    description="一个简单的 FastAPI 应用，用于模拟响应 MCP 请求，主要用于 A2A-to-MCP Adapter 演示。",
    version="0.1.0",
)

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """处理发送到 /mcp 的 POST 请求，模拟 MCP 服务行为"""
    request_id = "unknown" # Default if parsing fails or ID is missing
    try:
        body = await request.json()
        print("--- 模拟 MCP 服务收到请求 ---")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        print("--------------------------")

        # 尝试获取 JSON-RPC 请求 ID 和方法
        request_id = body.get('id')
        method = body.get('method')
        params = body.get('params')

        if method == "tools/call":
            # 模拟成功的响应
            response_payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "status": "success",
                    "message": "模拟工具调用成功！",
                    "output": {
                        "content": f"这是对方法 '{method}' 和参数 {params} 的模拟响应。"
                    }
                }
            }
            print("--- 模拟 MCP 服务发送成功响应 ---")
            print(json.dumps(response_payload, indent=2, ensure_ascii=False))
            print("-----------------------------")
            return JSONResponse(content=response_payload)
        else:
            # 模拟方法未找到的错误
            error_payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": "Method not found",
                    "data": f"方法 '{method}' 在此模拟服务中未实现。"
                }
            }
            print("--- 模拟 MCP 服务发送错误响应 (Method Not Found) ---")
            print(json.dumps(error_payload, indent=2, ensure_ascii=False))
            print("---------------------------------------------------")
            # 根据 JSON-RPC 规范，即使是错误响应，HTTP 状态码通常也是 200
            # 但如果需要，也可以返回 400 或 500 系列错误
            return JSONResponse(content=error_payload)

    except json.JSONDecodeError:
        print("错误：无法解析请求体为 JSON")
        # 返回 JSON-RPC 解析错误
        error_payload = {
            "jsonrpc": "2.0",
            "id": None, # ID 未知，因为无法解析请求
            "error": {
                "code": -32700,
                "message": "Parse error",
                "data": "无法将请求体解析为有效的 JSON。"
            }
        }
        # 对于解析错误，返回 400 Bad Request 可能更合适
        return JSONResponse(content=error_payload, status_code=400)
    except Exception as e:
        print(f"处理请求时发生意外错误: {e}")
        # 返回内部错误
        error_payload = {
            "jsonrpc": "2.0",
            "id": request_id, # 尝试使用之前获取的 ID
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": f"处理请求时发生服务器内部错误: {str(e)}"
            }
        }
        # 对于内部错误，返回 500 Internal Server Error
        return JSONResponse(content=error_payload, status_code=500)

if __name__ == "__main__":
    print("启动模拟 MCP 服务，监听 http://localhost:8001")
    # 运行 uvicorn 服务器
    # host="0.0.0.0" 表示监听所有可用网络接口，方便从容器或其他机器访问
    # 如果只需要本机访问，可以使用 host="127.0.0.1" 或 host="localhost"
    # reload=True 在开发时很有用，代码更改时会自动重启服务，但在 run_demo.sh 中可能不需要
    uvicorn.run("service:app", host="127.0.0.1", port=8001, log_level="info") 