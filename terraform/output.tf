output "api_url" {
  value = aws_apigatewayv2_api.api.api_endpoint
}

output "order_queue_url" {
  value = aws_sqs_queue.order_processing.url
}

output "order_queue_dlq_url" {
  value = aws_sqs_queue.order_processing_dlq.url
}

output "orders_table_name" {
  value = aws_dynamodb_table.orders.name
}
