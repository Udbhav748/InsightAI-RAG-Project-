terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # The state bucket and lock table must exist before `terraform init` can
  # bind to this backend — Terraform can't create its own backend storage
  # in the same config that uses it. Create them manually first (see
  # infra/README.md Step 0), then replace the bucket name below with the
  # real one before running `terraform init`.
  backend "s3" {
    bucket         = "insightai-rag-tfstate-618788620038"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "insightai-rag-tf-locks"
    encrypt        = true
  }
}
