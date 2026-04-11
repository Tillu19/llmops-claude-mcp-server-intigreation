import json
import os
import sys
import traceback

from flask import Flask, jsonify, request

from order_service import (
    CLAUDE_MODEL,
    build_summary,
    customer_answer,
    get_order,
    get_runtime_config,
    place_order,
)

SERVER_INFO = {
    "name": "order-workshop-mcp",
    "version": "1.0.0",
}

TOOLS = [
    {
        "name": "place_order",
        "description": "Create a new order through the AWS API Gateway endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "orderId": {"type": "string"},
                "item": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1},
                "customerName": {"type": "string"},
                "shippingAddress": {"type": "string"},
                "customerQuery": {"type": "string"},
            },
            "required": ["item"],
        },
    },
    {
        "name": "get_order",
        "description": "Fetch the full order record from DynamoDB by order ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"orderId": {"type": "string"}},
            "required": ["orderId"],
        },
    },
    {
        "name": "get_order_status",
        "description": "Return the current status of an order.",
        "inputSchema": {
            "type": "object",
            "properties": {"orderId": {"type": "string"}},
            "required": ["orderId"],
        },
    },
    {
        "name": "summarize_order",
        "description": "Create a human-readable summary of an order.",
        "inputSchema": {
            "type": "object",
            "properties": {"orderId": {"type": "string"}},
            "required": ["orderId"],
        },
    },
    {
        "name": "answer_customer_query",
        "description": "Use Claude to answer a customer's question about their order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "orderId": {"type": "string"},
                "question": {"type": "string"},
            },
            "required": ["orderId", "question"],
        },
    },
    {
        "name": "get_workshop_config",
        "description": "Return the active runtime configuration for the workshop demo.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def read_message():
    content_length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        header = line.decode("utf-8").strip()
        if header.lower().startswith("content-length:"):
            content_length = int(header.split(":", 1)[1].strip())

    if content_length is None:
        return None

    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def send_message(payload):
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def send_response(message_id, result):
    send_message({"jsonrpc": "2.0", "id": message_id, "result": result})


def send_error(message_id, code, message):
    send_message(
        {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": code, "message": message},
        }
    )


def text_result(text, structured_content=None):
    result = {"content": [{"type": "text", "text": text}]}
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return result


def require_string(arguments, field_name):
    value = (arguments or {}).get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field_name}' is required and must be a non-empty string.")
    return value.strip()


def handle_tool_call(tool_name, arguments):
    if tool_name == "place_order":
        payload = dict(arguments or {})
        if "item" not in payload or not str(payload["item"]).strip():
            raise ValueError("'item' is required.")
        if "quantity" in payload:
            payload["quantity"] = int(payload["quantity"])
        data, status_code = place_order(payload)
        return text_result(
            f"Order API responded with HTTP {status_code}.",
            {"statusCode": status_code, "response": data},
        )

    if tool_name == "get_order":
        order_id = require_string(arguments, "orderId")
        order = get_order(order_id)
        if not order:
            raise LookupError("Order not found")
        return text_result(json.dumps(order, indent=2, default=str), {"order": order})

    if tool_name == "get_order_status":
        order_id = require_string(arguments, "orderId")
        order = get_order(order_id)
        if not order:
            raise LookupError("Order not found")
        status = order.get("status", "unknown")
        return text_result(f"Order {order_id} status: {status}", {"status": status})

    if tool_name == "summarize_order":
        order_id = require_string(arguments, "orderId")
        order = get_order(order_id)
        if not order:
            raise LookupError("Order not found")
        summary = build_summary(order)
        return text_result(summary, {"summary": summary})

    if tool_name == "answer_customer_query":
        order_id = require_string(arguments, "orderId")
        question = require_string(arguments, "question")
        answer = customer_answer(order_id, question, use_claude=True)
        return text_result(answer, {"answer": answer})

    if tool_name == "get_workshop_config":
        config = get_runtime_config()
        return text_result(json.dumps(config, indent=2), config)

    raise ValueError(f"Unknown tool: {tool_name}")


def handle_request_payload(method, params=None):
    params = params or {}

    if method == "initialize":
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"tools": TOOLS}

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        return handle_tool_call(tool_name, arguments)

    raise NotImplementedError(f"Method not found: {method}")


def handle_request(message):
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})

    try:
        result = handle_request_payload(method, params)
        if method != "notifications/initialized":
            send_response(message_id, result)
    except LookupError as exc:
        send_error(message_id, -32001, str(exc))
    except ValueError as exc:
        send_error(message_id, -32602, str(exc))
    except NotImplementedError as exc:
        send_error(message_id, -32601, str(exc))
    except Exception as exc:
        send_error(message_id, -32000, f"{exc}\n{traceback.format_exc(limit=1)}")


http_app = Flask(__name__)


def build_cors_headers():
    allowed_origin = os.environ.get("MCP_ALLOWED_ORIGIN", "*").strip() or "*"
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


@http_app.after_request
def add_cors_headers(response):
    for header_name, header_value in build_cors_headers().items():
        response.headers[header_name] = header_value
    return response


@http_app.route("/mcp/call", methods=["OPTIONS"])
@http_app.route("/mcp/tools", methods=["OPTIONS"])
@http_app.route("/health", methods=["OPTIONS"])
def http_options():
    return ("", 204, build_cors_headers())


@http_app.get("/health")
def health_check():
    config = get_runtime_config()
    return jsonify(
        {
            "status": "ok",
            "serverInfo": SERVER_INFO,
            "anthropicConfigured": config["anthropicConfigured"],
        }
    )


@http_app.get("/mcp/tools")
def list_tools_http():
    return jsonify({"serverInfo": SERVER_INFO, "tools": TOOLS})


@http_app.post("/mcp/call")
def call_tool_http():
    payload = request.get_json() or {}
    tool_name = payload.get("name")
    arguments = payload.get("arguments", {})

    try:
        result = handle_tool_call(tool_name, arguments)
        return jsonify({"ok": True, "result": result})
    except LookupError as exc:
        return jsonify({"ok": False, "error": {"code": -32001, "message": str(exc)}}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": {"code": -32602, "message": str(exc)}}), 400
    except Exception as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": -32000,
                        "message": f"{exc}\n{traceback.format_exc(limit=1)}",
                    },
                }
            ),
            500,
        )


def run_stdio_server():
    print("MCP server ready on stdio", file=sys.stderr, flush=True)
    while True:
        message = read_message()
        if message is None:
            break
        handle_request(message)


def run_http_server():
    host = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
    http_app.run(host=host, port=port)


if __name__ == "__main__":
    mode = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if "--http" in sys.argv or mode == "http":
        run_http_server()
    else:
        run_stdio_server()
