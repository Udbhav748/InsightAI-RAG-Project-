# Reintroduced (an earlier version of this Lambda design deliberately left
# secrets as plain Lambda environment variables, reasoning that Lambda's
# own AWS-managed-KMS-key at-rest encryption made SSM unnecessary). That
# reasoning missed a real gap: lambda:GetFunction/GetFunctionConfiguration
# (needed by the CI deploy role — infra/github_oidc.tf — to poll deploy
# status) return environment variables *decrypted* by default, so any
# principal with those two read-only actions could see the plaintext
# secrets. Routing secrets through SSM instead closes that: the CI role
# never needs any SSM permission at all, so it never sees these values in
# any form. The app resolves them itself at cold start (see
# backend/app/core/config.py's _load_secrets_from_ssm(), called before
# Settings() is constructed) via a single SSM parameter-path prefix passed
# in as one env var (SECRETS_SSM_PREFIX, infra/lambda.tf) — never the
# secret values themselves.
#
# SecureString, not Secrets Manager: no per-secret monthly charge, and
# get_parameter(WithDecryption=True) is exactly as capable here.
#
# These plaintext values pass through Terraform state — the state bucket
# (infra/versions.tf, created manually per infra/README.md) must stay
# encrypted and non-public, the same "state file is sensitive" property
# any Terraform-managed secret has anywhere.

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
  # SSM SecureString rejects an empty string, so this parameter is only
  # created when a real DSN is supplied. The app's SSM loader
  # (config.py) simply doesn't find a DATABASE_URL parameter under the
  # prefix in that case and leaves Settings.database_url at its own
  # default ("") — no placeholder value is ever created or read.
  count = var.database_url != "" ? 1 : 0

  name  = "${local.ssm_prefix}/database_url"
  type  = "SecureString"
  value = var.database_url
}
