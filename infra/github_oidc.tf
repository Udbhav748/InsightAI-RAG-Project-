# OIDC federation for GitHub Actions — no long-lived AWS access keys stored
# as GitHub secrets. AWS trusts short-lived tokens GitHub itself issues,
# scoped to this specific repo via the trust policy condition below.

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # thumbprint_list intentionally omitted: current aws provider versions
  # auto-manage the thumbprint for this well-known GitHub-hosted provider.
}

data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to any ref on this repo. Tighten to
    # "repo:${var.github_repo}:ref:refs/heads/main" to restrict this role
    # to main-branch pushes only, the recommended posture given this role
    # can push images and update the deployed Lambda function.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy" {
  name               = "${var.project_name}-github-actions-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json
}

data "aws_iam_policy_document" "github_actions_deploy" {
  statement {
    sid       = "ECRAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # required by the API — this action has no resource-level scoping
  }

  statement {
    sid = "ECRPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  statement {
    sid = "LambdaDeploy"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
    ]
    resources = [aws_lambda_function.backend.arn]
    # GetFunction/GetFunctionConfiguration return Lambda environment
    # variables decrypted by default — this role needs GetFunction for
    # `aws lambda wait function-updated` to poll deploy status. That used
    # to mean this role could read the app's plaintext secrets, back when
    # they lived directly in the environment block. Not anymore: secrets
    # now resolve from SSM at cold start (see infra/ssm.tf,
    # backend/app/core/config.py's _load_secrets_from_ssm()) — the
    # environment block only carries SECRETS_SSM_PREFIX (a parameter
    # path, not a value), and this role has no ssm:* permission at all,
    # so it never sees the secrets in any form. Gap closed, not just
    # documented as accepted.
  }

  statement {
    sid = "FrontendDeploy"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [aws_s3_bucket.frontend.arn, "${aws_s3_bucket.frontend.arn}/*"]
  }

  statement {
    sid       = "FrontendInvalidate"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [aws_cloudfront_distribution.frontend.arn]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name   = "${var.project_name}-deploy"
  role   = aws_iam_role.github_actions_deploy.id
  policy = data.aws_iam_policy_document.github_actions_deploy.json
}
