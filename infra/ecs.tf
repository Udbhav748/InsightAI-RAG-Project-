resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # has its own CloudWatch cost; enable later if deeper per-task metrics are needed
  }
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.project_name}-backend"
  retention_in_days = 14
  # app/core/logging.py's JSONFormatter already writes structured JSON
  # lines to stdout — this log group receives that unchanged via the
  # awslogs driver below, directly queryable with CloudWatch Logs Insights.
}

locals {
  # DATABASE_URL is only injected when a real DSN was supplied — see the
  # comment in ssm.tf on why a placeholder value must never be passed.
  backend_secrets = concat(
    [
      { name = "GEMINI_API_KEY", valueFrom = aws_ssm_parameter.gemini_api_key.arn },
      { name = "API_KEY", valueFrom = aws_ssm_parameter.api_key.arn },
      { name = "GROQ_API_KEY", valueFrom = aws_ssm_parameter.groq_api_key.arn },
    ],
    var.database_url != "" ? [{ name = "DATABASE_URL", valueFrom = aws_ssm_parameter.database_url[0].arn }] : []
  )
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.fargate_cpu
  memory                   = var.fargate_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [
        { containerPort = 8000, protocol = "tcp" }
      ]

      # Non-secret config, carried over from render.yaml's reasoning:
      # groq (not gemini) because Gemini's free tier caps at 20 req/day;
      # hybrid search is pure-CPU with no extra model loaded; reranking is
      # off because it was never verified to fit Render's 512MB — worth
      # revisiting now that Fargate has 1GB+, but out of scope here.
      environment = [
        { name = "APP_NAME", value = "InsightAI-RAG" },
        { name = "DEBUG", value = "false" },
        { name = "LLM_PROVIDER", value = "groq" },
        { name = "HYBRID_SEARCH_ENABLED", value = "true" },
        { name = "RERANKING_ENABLED", value = "false" },
        { name = "FRONTEND_URL", value = var.frontend_url },
      ]

      secrets = local.backend_secrets

      mountPoints = [
        { sourceVolume = "uploads", containerPath = "/app/uploads", readOnly = false },
        { sourceVolume = "vector_store", containerPath = "/app/vector_store", readOnly = false },
        { sourceVolume = "feedback", containerPath = "/app/feedback", readOnly = false },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }
    }
  ])

  volume {
    name = "uploads"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.app_data.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.uploads.id
        iam             = "ENABLED"
      }
    }
  }

  volume {
    name = "vector_store"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.app_data.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.vector_store.id
        iam             = "ENABLED"
      }
    }
  }

  volume {
    name = "feedback"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.app_data.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.feedback.id
        iam             = "ENABLED"
      }
    }
  }
}

resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for s in aws_subnet.public : s.id]
    security_groups  = [aws_security_group.ecs_task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  # Matches the Dockerfile's own documented ~76s cold start (torch +
  # sentence-transformers import before uvicorn starts listening) — without
  # this grace period the ALB marks the task unhealthy and cycles it before
  # it ever comes up.
  health_check_grace_period_seconds = 90

  depends_on = [aws_lb_listener.http]

  lifecycle {
    # CI (deploy-backend.yml) registers new task-definition revisions and
    # force-deploys directly via the AWS CLI. Without this, the next
    # `terraform apply` would see task_definition as drifted from what's in
    # state and revert the service back to whatever revision Terraform last
    # knew about — Terraform owns the task definition's *shape*, CI owns
    # which revision is *currently running*.
    ignore_changes = [task_definition]
  }
}
