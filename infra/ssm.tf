# SSM Parameter Store SecureString, not Secrets Manager: no per-secret
# monthly charge, and the ECS task definition's `secrets` field supports
# both identically at this scale.
#
# These plaintext values pass through Terraform state. The state bucket
# (created manually per infra/README.md Step 0, before this config can even
# be applied) MUST have default encryption enabled and a bucket policy
# denying non-TLS and public access — the same "state file is sensitive"
# property any Terraform-managed secret has anywhere, called out explicitly
# rather than assumed.

locals {
  ssm_prefix = "/${var.project_name}/${var.environment}"
}

resource "aws_ssm_parameter" "gemini_api_key" {
  name  = "${local.ssm_prefix}/gemini_api_key"
  type  = "SecureString"
  value = var.gemini_api_key
}

resource "aws_ssm_parameter" "api_key" {
  name  = "${local.ssm_prefix}/api_key"
  type  = "SecureString"
  value = var.api_key
}

resource "aws_ssm_parameter" "groq_api_key" {
  name  = "${local.ssm_prefix}/groq_api_key"
  type  = "SecureString"
  value = var.groq_api_key
}

resource "aws_ssm_parameter" "database_url" {
  # SSM SecureString rejects an empty string value, so this parameter is
  # only created when a real DSN is supplied. app/core/database.py does
  # `if settings.database_url:` — any non-empty value (including a sentinel
  # like "unset") would be treated as a real DSN and passed straight to
  # create_engine(), crashing startup. So when no DATABASE_URL is provided,
  # the ECS task definition (ecs.tf) must omit the DATABASE_URL secret
  # entry entirely rather than inject a placeholder — Settings.database_url
  # then falls back to its own default of "", matching current behavior.
  count = var.database_url != "" ? 1 : 0

  name  = "${local.ssm_prefix}/database_url"
  type  = "SecureString"
  value = var.database_url
}
