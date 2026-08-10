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
    # can push images and mutate the running ECS service.
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
    sid     = "ECSDeployService"
    actions = ["ecs:UpdateService", "ecs:DescribeServices"]
    # aws_ecs_service.id is the full service ARN, not a short cluster/service
    # id, as long as the AWS account has ECS long-ARN-format enabled — true
    # by default for every account since AWS made it mandatory in 2021, so
    # safe to assume for a new account, but noted here rather than silently
    # assumed.
    resources = [aws_ecs_service.backend.id]
  }

  statement {
    sid     = "ECSDeployTaskDefinition"
    actions = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
    # Neither action supports resource-level restriction in IAM — AWS
    # requires resources = ["*"] here regardless of scoping intent.
    resources = ["*"]
  }

  statement {
    sid       = "PassEcsRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.ecs_task_execution.arn, aws_iam_role.ecs_task.arn]
    # Required for ecs:RegisterTaskDefinition to hand the execution/task
    # roles to the new revision.
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
