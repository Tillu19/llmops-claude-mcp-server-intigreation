import json
import os
from pathlib import Path
from urllib import error, request as urlrequest

import boto3

CLAUDE_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


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

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ORDERS_TABLE = os.environ.get("ORDERS_TABLE", "Orders")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
ORDER_API_URL = os.environ.get("ORDER_API_URL", "")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(ORDERS_TABLE)


def get_runtime_config():
    return {
        "awsRegion": AWS_REGION,
        "ordersTable": ORDERS_TABLE,
        "claudeModel": CLAUDE_MODEL,
        "orderApiUrl": ORDER_API_URL,
        "anthropicConfigured": bool(ANTHROPIC_API_KEY),
    }


def get_order(order_id):
    response = table.get_item(Key={"orderId": order_id})
    return response.get("Item")


def build_summary(order):
    return (
        f"Order {order['orderId']} for {order.get('customerName', 'Guest')} contains "
        f"{order.get('quantity', 1)} x {order.get('item', 'unknown item')}. "
        f"Current status is {order.get('status', 'unknown')}, payment is "
        f"{order.get('paymentStatus', 'pending')}, and shipping is "
        f"{order.get('shippingStatus', 'pending')}."
    )


def fallback_answer(order, question):
    question_normalized = (question or "").lower()
    if "status" in question_normalized:
        return (
            f"Your order {order['orderId']} is currently {order.get('status', 'unknown')}."
        )
    if "payment" in question_normalized:
        return (
            f"Payment for order {order['orderId']} is "
            f"{order.get('paymentStatus', 'pending')}."
        )
    if "shipping" in question_normalized or "delivery" in question_normalized:
        return (
            f"Shipping for order {order['orderId']} is "
            f"{order.get('shippingStatus', 'pending')}."
        )
    return build_summary(order)


def ask_claude(order, question):
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set.")

    order_context = json.dumps(order, indent=2, default=str)
    body = {
        "model": CLAUDE_MODEL,
        "temperature": 0.5,
        "max_tokens": 300,
        "system": (
            "You are a helpful customer support assistant for an order processing system. "
            "Answer in plain English that is easy to understand. "
            "Use the customer's question and the full order data carefully. "
            "Give a complete answer, not just a one-line status. "
            "When relevant, mention the item, quantity, current order status, payment status, "
            "shipping status, shipping address, and the likely next step. "
            "If the customer asks a direct question, answer that first and then add a short helpful explanation. "
            "Do not mention JSON, databases, DynamoDB, internal fields, or raw object names."
        ),
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Customer question:\n{question}\n\n"
                            f"Order details:\n{order_context}\n\n"
                            "Write the reply as if you are speaking to the customer directly."
                        ),
                    }
                ],
            }
        ],
    }

    claude_request = urlrequest.Request(
        CLAUDE_MESSAGES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "order-ai-demo/1.0",
        },
        method="POST",
    )

    try:
        with urlrequest.urlopen(claude_request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise RuntimeError(f"Claude HTTP {exc.code}: {error_body}") from exc

    content = payload.get("content", [])
    text_parts = [
        block.get("text", "").strip()
        for block in content
        if block.get("type") == "text" and block.get("text")
    ]
    return "\n".join(text_parts).strip()


def place_order(payload):
    if not ORDER_API_URL:
        raise ValueError("ORDER_API_URL is not configured.")

    api_request = urlrequest.Request(
        ORDER_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlrequest.urlopen(api_request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8") or "{}"
        try:
            return json.loads(error_body), exc.code
        except json.JSONDecodeError:
            return {"message": error_body or "Order API request failed"}, exc.code


def customer_answer(order_id, question, use_claude=True):
    order = get_order(order_id)
    if not order:
        raise LookupError("Order not found")

    if use_claude:
        return ask_claude(order, question)
    return fallback_answer(order, question)
