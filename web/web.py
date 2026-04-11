import json
import os
import uuid
from datetime import datetime, timezone

import boto3

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "Orders")
ORDER_QUEUE_URL = os.environ.get("ORDER_QUEUE_URL")

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")
table = dynamodb.Table(TABLE_NAME)


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _process_order(order_id):
    now = _timestamp()

    response = table.get_item(Key={"orderId": order_id})
    order = response.get("Item")

    if not order:
        raise ValueError(f"Order {order_id} not found.")

    table.update_item(
        Key={"orderId": order_id},
        UpdateExpression=(
            "SET #status = :status, "
            "paymentStatus = :payment_status, "
            "shippingStatus = :shipping_status, "
            "lastUpdated = :last_updated"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "processed",
            ":payment_status": "paid",
            ":shipping_status": "ready_for_dispatch",
            ":last_updated": now,
        },
    )

    return {
        "orderId": order_id,
        "status": "processed",
        "processedAt": now,
    }


def _handle_sqs_event(event):
    processed_orders = []

    for record in event.get("Records", []):
        body = json.loads(record.get("body") or "{}")
        order_id = body.get("orderId")

        if not order_id:
            raise ValueError("SQS message is missing orderId.")

        processed_orders.append(_process_order(order_id))

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Processed queued orders.",
                "processedOrders": processed_orders,
            }
        ),
    }


def _handle_api_event(event):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"message": "Request body must be valid JSON."})

    item = body.get("item")
    customer_query = body.get("customerQuery")
    quantity = body.get("quantity", 1)

    if not item:
        return _response(400, {"message": "The 'item' field is required."})

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return _response(400, {"message": "The 'quantity' field must be a number."})

    if quantity < 1:
        return _response(400, {"message": "The 'quantity' field must be at least 1."})

    if not ORDER_QUEUE_URL:
        return _response(500, {"message": "ORDER_QUEUE_URL is not configured."})

    order_id = body.get("orderId") or str(uuid.uuid4())
    created_at = _timestamp()

    order = {
        "orderId": order_id,
        "item": item,
        "quantity": quantity,
        "customerName": body.get("customerName", "Guest"),
        "shippingAddress": body.get("shippingAddress", "Not provided"),
        "customerQuery": customer_query,
        "status": "queued",
        "paymentStatus": "pending",
        "shippingStatus": "pending",
        "createdAt": created_at,
        "lastUpdated": created_at,
    }

    table.put_item(Item=order)

    try:
        sqs.send_message(
            QueueUrl=ORDER_QUEUE_URL,
            MessageBody=json.dumps(
                {
                    "orderId": order_id,
                    "createdAt": created_at,
                }
            ),
        )
    except Exception as exc:
        table.delete_item(Key={"orderId": order_id})
        return _response(
            502,
            {
                "message": "Failed to queue order for processing.",
                "error": str(exc),
            },
        )

    return _response(
        200,
        {
            "message": "Order created and queued successfully.",
            "orderId": order_id,
            "status": "queued",
        },
    )


def lambda_handler(event, context):
    if event.get("Records") and event["Records"][0].get("eventSource") == "aws:sqs":
        return _handle_sqs_event(event)

    return _handle_api_event(event)
