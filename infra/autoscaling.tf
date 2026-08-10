# Known, unresolved limitation introduced by this policy:
#
# backend/app/services/faiss_vector_store.py protects index writes with an
# in-process threading.Lock only — safe within a single ECS task, NOT safe
# across two tasks concurrently writing the same EFS-mounted index.faiss /
# metadata.json. Reads (chat/query retrieval) are fine to serve from N
# concurrent tasks once the on-disk files are stable. But two tasks handling
# concurrent POST /upload or DELETE /documents/{id} requests can corrupt the
# index — save()/load() aren't atomic across processes, so this is a real
# risk, not a theoretical one, whenever max_capacity > 1.
#
# A second, pre-existing single-instance assumption this same setting
# reactivates: app/services/session_store.py's in-memory chat-history store
# is documented (docs/DESIGN_REVIEW.md, Q9) as correct ONLY while the
# service runs as exactly one process — on Render's free tier that was
# always true (no autoscaling existed there), so it was a dormant
# correctness bound, not a live bug. With autoscaling_max_capacity > 1
# here, it stops being dormant: a session created on one task is invisible
# to a request landing on another. session_store.py already has the fix
# built in — it routes to PostgresSessionStore automatically whenever
# DATABASE_URL is set (see infra/variables.tf's database_url variable) —
# so max_capacity > 1 should not be used without also setting database_url.
#
# This is documented here, not mitigated. Options, not implemented in this
# Terraform:
#   (a) set autoscaling_max_capacity = 1 in terraform.tfvars — eliminates
#       both risks (FAISS and sessions) entirely, at the cost of no
#       horizontal scaling.
#   (b) set database_url (Postgres) to fix sessions, AND migrate to a
#       concurrency-safe vector store (pgvector, a managed vector DB) to
#       fix FAISS, before relying on max_capacity > 1 in production.
#   (c) accept the risk short-term for read-mostly traffic.

resource "aws_appautoscaling_target" "backend" {
  min_capacity       = 1
  max_capacity       = var.autoscaling_max_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${var.project_name}-backend-cpu-target-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 65
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
