variable "aws_region" {
  description = "AWS region for all resources. CloudFront itself is global regardless."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "insightai-rag"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "image_tag" {
  description = <<-EOT
    Tag the Lambda function's image_uri points at. The deployed function
    always references the sha CI just built; CI updates it directly via
    `aws lambda update-function-code --image-uri <repo>:<sha>` and
    Terraform ignores drift on image_uri (see lambda.tf's lifecycle block).
    Rolling back means pointing update-function-code at a known-good sha,
    not changing this variable.
  EOT
  type        = string
  default     = "latest"
}

variable "lambda_memory_mb" {
  description = <<-EOT
    Lambda memory (128-10240 MB) — CPU scales proportionally with this.
    2048 is double Fargate's 1024MiB: Lambda's Init phase (torch/
    sentence-transformers import + model load) is hard-capped at 10s on a
    cold environment; more memory buys more CPU, shortening how much of
    that spills into the first real request's own timeout budget.
  EOT
  type        = number
  default     = 2048
}

variable "lambda_timeout_seconds" {
  description = <<-EOT
    Must additively cover: deferred Init (if the 10s cap was hit) +
    research_total_timeout_seconds (45, backend/app/core/config.py) + LLM
    synthesis + adapter overhead. A genuinely new consideration Fargate
    never had — its health_check_grace_period_seconds absorbed cold start
    entirely outside any single request's timeout; Lambda's retried-Init
    mechanic eats into the first request's own timeout instead.
  EOT
  type        = number
  default     = 120
}

variable "lambda_ephemeral_storage_mb" {
  description = <<-EOT
    /tmp size (512-10240 MB). Doubled from Lambda's 512MB default since
    /tmp also holds the HF model cache copy (entrypoint.sh) plus
    uploads/vector_store/feedback.
  EOT
  type        = number
  default     = 1024
}

variable "gemini_api_key" {
  description = "Required. Passed to the Lambda function as an environment variable, encrypted at rest by Lambda's default AWS-managed KMS key."
  type        = string
  sensitive   = true
}

variable "api_key" {
  description = "Required. The backend's own X-API-Key auth secret (see backend/app/core/auth.py)."
  type        = string
  sensitive   = true
}

variable "groq_api_key" {
  description = "Optional (LLM_PROVIDER defaults to groq — required in practice unless switched to gemini)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "database_url" {
  description = "Optional Postgres DSN. Empty string matches Settings.database_url's own default."
  type        = string
  sensitive   = true
  default     = ""
}

variable "frontend_url" {
  description = <<-EOT
    The frontend CloudFront domain, e.g. "https://dxxxxx.cloudfront.net" — used
    for CORS (main.py's CORSMiddleware is a single-origin allowlist). Left
    empty on the first apply (the frontend distribution doesn't exist yet);
    fill in from `terraform output frontend_cloudfront_domain` and apply again.
    See infra/README.md's two-phase-apply note.
  EOT
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "owner/repo, used in the GitHub OIDC trust policy condition."
  type        = string
  default     = "Udbhav748/InsightAI-RAG-Project-"
}
