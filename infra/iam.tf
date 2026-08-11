# Lambda has one execution role, not ECS's execution-role/task-role split
# — there's no separate "what launches the container" vs. "what the app
# calls" distinction in Lambda the way there was for Fargate.
#
# SSM read permission below: the app itself now calls the SSM SDK at cold
# start to resolve secrets (backend/app/core/config.py's
# _load_secrets_from_ssm()) — see infra/ssm.tf's header comment for why
# this replaced the earlier "just use plain Lambda env vars" design (it
# left secrets readable in plaintext by anything with
# lambda:GetFunctionConfiguration, including the CI deploy role below).

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

# Scoped to this app's own SSM path prefix only — not ssm:*, not resource "*".
data "aws_iam_policy_document" "lambda_ssm" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*"]
  }
}

resource "aws_iam_role_policy" "lambda_ssm" {
  name   = "${var.project_name}-lambda-ssm"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_ssm.json
}
