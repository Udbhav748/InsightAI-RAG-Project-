# AWS managed policies (no custom cache/origin-request policy needed):
#   CachingDisabled            - this is a dynamic authenticated API, not
#                                cacheable content.
#   AllViewerExceptHostHeader  - forwards all viewer headers (except Host)
#                                to the origin. This is load-bearing: without
#                                it, CloudFront's default behavior strips
#                                X-API-Key, and every authenticated request
#                                (app/core/auth.py) would 401.
locals {
  cloudfront_caching_disabled_policy_id      = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  cloudfront_all_viewer_except_host_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
}

resource "aws_cloudfront_distribution" "backend" {
  enabled = true

  origin {
    domain_name = aws_lb.backend.dns_name
    origin_id   = "backend-alb"

    custom_origin_config {
      http_port              = 80
      https_port              = 443
      origin_protocol_policy  = "http-only" # ALB has no HTTPS listener — see alb.tf
      origin_ssl_protocols    = ["TLSv1.2"]

      # CloudFront's own default origin_read_timeout is 30s — well under
      # research_total_timeout_seconds (45, backend/app/core/config.py) plus
      # synthesis time. Without raising this, CloudFront itself would cut off
      # exactly the slow research-agent requests alb.tf's 90s idle_timeout
      # was set to accommodate, before the ALB's timeout ever came into play.
      # 60s is CloudFront's hard maximum for both settings — not quite the
      # full 90s the ALB allows, but the largest ceiling CloudFront permits.
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
    }
  }

  default_cache_behavior {
    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "backend-alb"

    viewer_protocol_policy    = "redirect-to-https"
    cache_policy_id           = local.cloudfront_caching_disabled_policy_id
    origin_request_policy_id  = local.cloudfront_all_viewer_except_host_policy_id
  }

  # Grants the free HTTPS cert on CloudFront's own *.cloudfront.net domain —
  # no ACM certificate or Route53 domain required.
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  price_class = "PriceClass_100" # cheapest edge tier (US/Canada/Europe) — fine for a portfolio demo

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  tags = {
    Name = "${var.project_name}-backend"
  }
}
