resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${var.project_name}-backend"
  retention_in_days = 14
  # app/core/logging.py's JSONFormatter already writes structured JSON
  # lines to stdout — Lambda ships that unchanged to this log group,
  # directly queryable via CloudWatch Logs Insights, same as the
  # superseded ECS design's log group.
}

locals {
  # Secrets go straight into plain environment variables (no SSM — see
  # iam.tf's header comment for why that's genuinely fine for Lambda).
  # Lambda encrypts these at rest by default with an AWS-managed KMS key.
  backend_env = {
    APP_NAME              = "InsightAI-RAG"
    DEBUG                 = "false"
    LLM_PROVIDER          = "groq"
    HYBRID_SEARCH_ENABLED = "true"
    RERANKING_ENABLED     = "false"
    FRONTEND_URL          = var.frontend_url
    GEMINI_API_KEY        = var.gemini_api_key
    API_KEY               = var.api_key
    GROQ_API_KEY          = var.groq_api_key
    DATABASE_URL          = var.database_url
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
  reserved_concurrent_executions = 1

  ephemeral_storage {
    size = var.lambda_ephemeral_storage_mb
  }

  environment {
    variables = local.backend_env
  }

  depends_on = [aws_cloudwatch_log_group.backend]

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
