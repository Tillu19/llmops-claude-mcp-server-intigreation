provider "aws" {
  region = var.region
}

resource "aws_sqs_queue" "order_processing" {
  name                       = "order-processing-queue"
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = 180
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.order_processing_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue" "order_processing_dlq" {
  name                    = "order-processing-dlq"
  sqs_managed_sse_enabled = true
}

resource "aws_iam_role" "order_api_lambda_role" {
  name = "order_api_demo_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "order_api_lambda_basic" {
  role       = aws_iam_role.order_api_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "order_api_lambda_access" {
  name = "order_api_demo_lambda_access"
  role = aws_iam_role.order_api_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = aws_dynamodb_table.orders.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueUrl",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.order_processing.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = aws_sqs_queue.order_processing.arn
      }
    ]
  })
}

resource "aws_dynamodb_table" "orders" {
  name         = "Orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "orderId"

  attribute {
    name = "orderId"
    type = "S"
  }
}

resource "aws_lambda_function" "order_api_lambda" {
  function_name = "order-api-demo"
  runtime       = "python3.11"
  handler       = "lambda_function.lambda_handler"
  role          = aws_iam_role.order_api_lambda_role.arn
  filename      = "${path.module}/lambda.zip"
  timeout       = 30
  memory_size   = 256

  source_code_hash = filebase64sha256("${path.module}/lambda.zip")

  environment {
    variables = {
      DYNAMODB_TABLE  = aws_dynamodb_table.orders.name
      ORDER_QUEUE_URL = aws_sqs_queue.order_processing.url
    }
  }
}

# resource "aws_cloudwatch_log_group" "order_api_lambda" {
#   name              = "/aws/lambda/${aws_lambda_function.order_api_lambda.function_name}"
#   retention_in_days = 14
# }

resource "aws_lambda_event_source_mapping" "order_api_sqs" {
  event_source_arn = aws_sqs_queue.order_processing.arn
  function_name    = aws_lambda_function.order_api_lambda.arn
  batch_size       = 10
  enabled          = true
}

resource "aws_apigatewayv2_api" "api" {
  name          = "order-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.order_api_lambda.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "route" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /order"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_stage" "stage" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.order_api_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
