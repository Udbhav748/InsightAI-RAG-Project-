# HTTP listener only — deliberately no HTTPS here. An ACM certificate
# requires domain ownership validation, and this deployment has no custom
# domain (see the plan's domain/HTTPS decision). TLS terminates at
# CloudFront (cloudfront_backend.tf) instead, using CloudFront's own free
# *.cloudfront.net certificate; traffic between CloudFront and this ALB is
# plain HTTP within AWS's network — the standard "TLS at the CDN, HTTP to
# origin" pattern, not equivalent to end-to-end TLS, stated here explicitly
# rather than left implicit.

resource "aws_lb" "backend" {
  name               = "${var.project_name}-backend"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [for s in aws_subnet.public : s.id]
  idle_timeout       = 90 # research agent calls can run up to ~45s + synthesis; default 60s is too tight

  tags = {
    Name = "${var.project_name}-backend"
  }
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-backend"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # required for Fargate awsvpc networking mode

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 30

  tags = {
    Name = "${var.project_name}-backend"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.backend.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
