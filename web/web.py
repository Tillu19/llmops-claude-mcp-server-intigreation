import json
import os
import traceback
from pathlib import Path
from urllib import error, request as urlrequest

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException


def load_env_file():
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')

        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()


class MCPClientError(RuntimeError):
    def __init__(self, message, code=None, status_code=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class RemoteMCPClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def call_tool(self, name, arguments=None):
        payload = {"name": name, "arguments": arguments or {}}
        endpoint = f"{self.base_url}/mcp/call"
        api_request = urlrequest.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urlrequest.urlopen(api_request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
                return self._parse_body(body, response.status)
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8") or "{}"
            try:
                body = json.loads(error_body)
            except json.JSONDecodeError as decode_error:
                raise MCPClientError(
                    f"MCP server HTTP {exc.code}: {error_body}",
                    status_code=exc.code,
                ) from decode_error
            return self._parse_body(body, exc.code)
        except error.URLError as exc:
            raise MCPClientError(f"Unable to reach MCP server at {endpoint}: {exc}") from exc
        except Exception as exc:
            raise MCPClientError(f"Unexpected MCP client failure: {exc}") from exc

    def _parse_body(self, body, status_code):
        if body.get("ok"):
            return body.get("result", {})

        error_info = body.get("error", {})
        raise MCPClientError(
            error_info.get("message", "MCP tool call failed"),
            code=error_info.get("code"),
            status_code=status_code,
        )


app = Flask(__name__)
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000")
mcp_client = RemoteMCPClient(MCP_SERVER_URL)


def text_from_result(result):
    content = result.get("content", [])
    text_parts = [
        block.get("text", "").strip()
        for block in content
        if block.get("type") == "text" and block.get("text")
    ]
    return "\n".join(part for part in text_parts if part).strip()


def unexpected_error_response(prefix, exc):
    app.logger.exception(prefix)
    return (
        jsonify(
            {
                "message": f"{prefix}: {exc}",
                "trace": traceback.format_exc(limit=1),
            }
        ),
        500,
    )


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    return jsonify({"message": exc.description, "statusCode": exc.code}), exc.code


@app.errorhandler(Exception)
def handle_unexpected_exception(exc):
    app.logger.exception("Unhandled application error")
    return (
        jsonify(
            {
                "message": f"Unhandled application error: {exc}",
                "trace": traceback.format_exc(limit=1),
                "mcpServerUrl": MCP_SERVER_URL,
            }
        ),
        500,
    )


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/placeOrder", methods=["POST"])
def place_order_route():
    payload = request.get_json(silent=True) or {}

    try:
        result = mcp_client.call_tool("place_order", payload)
        structured = result.get("structuredContent", {})
        return jsonify(structured.get("response", {})), structured.get("statusCode", 200)
    except MCPClientError as exc:
        return jsonify({"message": f"Unable to reach MCP order tool: {exc}"}), 502
    except Exception as exc:
        return unexpected_error_response("Unexpected placeOrder failure", exc)


@app.route("/getOrder", methods=["POST"])
def get_order_details():
    data = request.get_json(silent=True) or {}
    order_id = data.get("orderId")

    try:
        result = mcp_client.call_tool("get_order", {"orderId": order_id})
        order = (result.get("structuredContent") or {}).get("order")
        return jsonify({"order": order})
    except MCPClientError as exc:
        if exc.code == -32001:
            return jsonify({"message": "Order not found"}), 404
        return jsonify({"message": f"MCP get_order failed: {exc}"}), 502
    except Exception as exc:
        return unexpected_error_response("Unexpected getOrder failure", exc)


@app.route("/getOrderStatus", methods=["POST"])
def get_order_status():
    data = request.get_json(silent=True) or {}
    order_id = data.get("orderId")

    try:
        result = mcp_client.call_tool("get_order_status", {"orderId": order_id})
        status = (result.get("structuredContent") or {}).get("status")
        return jsonify({"status": status})
    except MCPClientError as exc:
        if exc.code == -32001:
            return jsonify({"status": "unknown"}), 404
        return jsonify({"message": f"MCP get_order_status failed: {exc}"}), 502
    except Exception as exc:
        return unexpected_error_response("Unexpected getOrderStatus failure", exc)


@app.route("/summarizeOrder", methods=["POST"])
def summarize_order():
    data = request.get_json(silent=True) or {}
    order_id = data.get("orderId")

    try:
        result = mcp_client.call_tool("summarize_order", {"orderId": order_id})
        summary = (result.get("structuredContent") or {}).get("summary") or text_from_result(result)
        return jsonify({"summary": summary})
    except MCPClientError as exc:
        if exc.code == -32001:
            return jsonify({"message": "Order not found"}), 404
        return jsonify({"message": f"MCP summarize_order failed: {exc}"}), 502
    except Exception as exc:
        return unexpected_error_response("Unexpected summarizeOrder failure", exc)


@app.route("/customerQuery", methods=["POST"])
def customer_query():
    data = request.get_json(silent=True) or {}
    order_id = data.get("orderId")
    question = data.get("question", "")

    try:
        result = mcp_client.call_tool(
            "answer_customer_query",
            {"orderId": order_id, "question": question},
        )
        answer = (result.get("structuredContent") or {}).get("answer") or text_from_result(result)
        return jsonify({"answer": answer})
    except MCPClientError as exc:
        if exc.code == -32001:
            return jsonify({"message": "Order not found"}), 404
        return jsonify({"message": f"Claude AI request failed through MCP: {exc}"}), 502
    except Exception as exc:
        return unexpected_error_response("Unexpected customerQuery failure", exc)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
