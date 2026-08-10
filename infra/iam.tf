# Lambda has one execution role, not ECS's execution-role/task-role split
# — there's no separate "what launches the container" vs. "what the app
# calls" distinction in Lambda the way there was for Fargate.
#
# No SSM here (unlike the superseded ecs.tf design): the app never calls
# the SSM SDK itself — SSM only existed as a delivery conduit for ECS's
# `secrets` field, which has no Lambda equivalent (Lambda environment
# variables are static strings set at function-config time, with no
# per-variable "resolve from SSM at launch" mechanism). Lambda encrypts
# environment variables at rest by default with an AWS-managed KMS key —
# the same at-rest protection SecureString gave, one fewer resource.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${var.project_name}-lambda-execution"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Scoped to this function's own log group only — not the AWS-managed
# AWSLambdaBasicExecutionRole's implicit arn:aws:logs:*:*:* wildcard.
data "aws_iam_policy_document" "lambda_logs" {
  statement {
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.backend.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda_logs" {
  name   = "${var.project_name}-lambda-logs"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_logs.json
}

data "aws_iam_policy_document" "lambda_s3_data" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data.arn}/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }
}

resource "aws_iam_role_policy" "lambda_s3_data" {
  name   = "${var.project_name}-lambda-s3-data"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_s3_data.json
}
