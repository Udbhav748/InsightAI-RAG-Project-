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
    Tag the ECS task definition points at. The running service always
    references ":latest"; CI pushes both ":latest" and ":<git-sha>" on every
    deploy, so rolling back means retagging a known-good sha as ":latest"
    and forcing a new deployment, not changing this variable.
  EOT
  type        = string
  default     = "latest"
}

variable "fargate_cpu" {
  description = "Task-level vCPU units (Fargate: 512 = 0.5 vCPU). A step up from Render free tier's 0.1 CPU / 512MB ceiling."
  type        = string
  default     = "512"
}

variable "fargate_memory" {
  description = "Task-level memory in MiB (Fargate: must be a valid pairing with fargate_cpu)."
  type        = string
  default     = "1024"
}

variable "autoscaling_max_capacity" {
  description = <<-EOT
    Max ECS tasks the service can scale out to. IMPORTANT: faiss_vector_store.py
    protects writes with an in-process threading.Lock only — safe within one
    task, NOT safe across multiple tasks writing the same EFS-mounted FAISS
    index concurrently. Reads scale fine; concurrent POST /upload or
    DELETE /documents/{id} across tasks can corrupt the index. Set this to 1
    to eliminate the risk entirely (autoscaling effectively disabled) until
    the vector store is replaced with something concurrency-safe. See
    autoscaling.tf for the full writeup.
  EOT
  type        = number
  default     = 2
}

variable "gemini_api_key" {
  description = "Required. Stored as an SSM SecureString, never in plain task-definition environment."
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
