resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${var.project_name}-backend"
  retention_in_days = 14
  # app/core/logging.py's JSONFormatter already writes structured JSON
  # lines to stdout — Lambda ships that unchanged to this log group,
  # directly queryable via CloudWatch Logs Insights, same as the
  # superseded ECS design's log group.
}

locals {
  # Secrets are NOT set directly here — SECRETS_SSM_PREFIX (below) is the
  # only secret-related thing in this env block: it's a parameter *path*,
  # not a value. backend/app/core/config.py's _load_secrets_from_ssm()
  # resolves GEMINI_API_KEY/API_KEY/GROQ_API_KEY/DATABASE_URL from SSM
  # SecureString parameters under this prefix at cold start, before
  # Settings() reads the environment — see infra/ssm.tf's header comment
  # for why plain env vars (an earlier version of this file) were replaced.
  backend_env = {
    APP_NAME              = "InsightAI-RAG"
    DEBUG                 = "false"
    LLM_PROVIDER          = "groq"
    HYBRID_SEARCH_ENABLED = "true"
    RERANKING_ENABLED     = "false"
    FRONTEND_URL          = var.frontend_url
    SECRETS_SSM_PREFIX    = local.ssm_prefix
    S3_SYNC_ENABLED       = "true"
    S3_SYNC_BUCKET_NAME   = aws_s3_bucket.data.bucket
    PORT                  = "8000"

    # AWS Lambda Web Adapter config (backend/Dockerfile). AWS_LWA_INVOKE_MODE
    # must match aws_lambda_function_url.backend's invoke_mode below exactly
    # — the two are configured independently and disagree silently
    # (buffered response instead of incremental) if they don't match.
    AWS_LWA_INVOKE_MODE          = "RESPONSE_STREAM"
    AWS_LWA_PORT                 = "8000"
    AWS_LWA_READINESS_CHECK_PATH = "/health"
  }
}

resource "aws_lambda_function" "backend" {
  function_name = "${var.project_name}-backend"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
  architectures = ["x86_64"]

  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_seconds

  # FAISS write-safety: faiss_vector_store.py's threading.Lock guards one
  # process, not two. Capping at 1 execution environment makes concurrent
  # writes structurally impossible instead of just unlikely — the same
  # property the superseded Fargate plan's desired_count=1 gave.
  # Consequence, stated plainly: a second request arriving while one is in
  # flight gets an immediate 429 (TooManyRequestsException), not queued —
  # a real behavioral difference from a single Fargate task's own uvicorn
  # process, which queues concurrent requests in-process instead.
  #
  # TEMPORARILY DISABLED, not removed for good: this AWS account is new and
  # unverified, capping its *total* Lambda concurrency at 10 account-wide
  # (`aws lambda get-account-settings`). AWS requires at least 10 to stay
  # unreserved after any reservation, so reserving even 1 here is
  # mathematically impossible on this account right now — every attempt
  # fails with "decreases account's UnreservedConcurrentExecution below its
  # minimum value of [10]". Until account verification completes (raises
  # the account-wide limit, typically to 1000), concurrent writes to the
  # S3-synced FAISS index are NOT structurally prevented — a real, accepted
  # short-term risk at this project's current near-zero traffic, not a
  # forgotten TODO. Re-add `reserved_concurrent_executions = 1` the moment
  # `aws lambda get-account-settings` shows AccountLimit.ConcurrentExecutions
  # above 10, then `terraform apply` again.
  # reserved_concurrent_executions = 1

  ephemeral_storage {
    size = var.lambda_ephemeral_storage_mb
  }

  environment {
    variables = local.backend_env
  }

  depends_on = [
    aws_cloudwatch_log_group.backend,
    aws_ssm_parameter.gemini_api_key,
    aws_ssm_parameter.api_key,
    aws_ssm_parameter.groq_api_key,
  ]

  lifecycle {
    # CI (deploy-backend.yml) updates the running image directly via
    # `aws lambda update-function-code`. Mirrors the superseded ecs.tf's
    # identical ignore_changes on task_definition — Terraform owns the
    # function's shape, CI owns which image is currently deployed.
    ignore_changes = [image_uri]
  }
}

resource "aws_lambda_function_url" "backend" {
  function_name = aws_lambda_function.backend.function_name

  # App-level X-API-Key auth (core/auth.py) is the real gate — matches the
  # prior ALB+CloudFront posture, neither of which added authentication either.
  authorization_type = "NONE"

  # Must match AWS_LWA_INVOKE_MODE above exactly — see that comment.
  invoke_mode = "RESPONSE_STREAM"

  # No cors {} block: CORSMiddleware (main.py) already handles CORS
  # end-to-end. A Function URL CORS config here would double-handle
  # preflight OPTIONS requests.
}

# authorization_type = "NONE" above only controls how AWS evaluates
# authorization — it does NOT by itself create a resource policy allowing
# anyone to actually invoke the URL. Without this explicit permission,
# every call 403s with AccessDeniedException regardless of auth_type.
resource "aws_lambda_permission" "function_url_public" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.backend.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
