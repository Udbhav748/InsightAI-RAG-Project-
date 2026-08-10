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
    # Documented trade-off, not fixed here: GetFunction/GetFunctionConfiguration
    # both return Lambda environment variables *decrypted* by default, so this
    # role (needed for `aws lambda wait function-updated`, which polls
    # GetFunction) can read the app's plaintext secrets. Closing this
    # properly needs a customer-managed KMS key with kms:Decrypt withheld
    # from this role — real complexity for unverified benefit at this
    # project's scale (a personal AWS account, a short-lived OIDC-issued
    # credential scoped to this one repo). Accepted and stated plainly,
    # the same way the FAISS-concurrency caveat is accepted and documented
    # rather than silently glossed over.
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
