# Persistence for the Lambda deployment's read-only-outside-/tmp
# filesystem — one bucket, three prefixes (uploads/, vector_store/,
# feedback/), matching s3_sync_service.py's prefix-based design. Mirrors
# s3_frontend.tf's pattern exactly. No versioning: this data is
# regenerable (re-upload, re-seed) and versioning would only add cost for
# no real benefit at this project's scale.

resource "aws_s3_bucket" "data" {
  bucket = "${var.project_name}-data-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
