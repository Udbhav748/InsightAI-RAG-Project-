output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "lambda_function_name" {
  value = aws_lambda_function.backend.function_name
}

output "lambda_function_url" {
  value = aws_lambda_function_url.backend.function_url
}

output "frontend_cloudfront_domain" {
  value = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}

output "frontend_s3_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "github_actions_role_arn" {
  value = aws_iam_role.github_actions_deploy.arn
}

output "aws_region" {
  value = var.aws_region
}
