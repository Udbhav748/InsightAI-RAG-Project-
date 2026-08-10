resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE" # :latest is overwritten every deploy by design

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Cost control: don't let old images accumulate indefinitely.
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        # tagStatus "any" (not "tagged" + tagPrefixList) deliberately: git
        # commit shas (deploy-backend.yml tags images with the raw
        # ${{ github.sha }}, e.g. "a1b2c3d...") don't start with any fixed
        # prefix, so a tagPrefixList-based rule would never match them and
        # images would accumulate unbounded. "any" counts every image
        # regardless of tag and expires the oldest beyond the threshold.
        description = "Keep only the last 15 images total (any tag)"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 15
        }
        action = { type = "expire" }
      }
    ]
  })
}
