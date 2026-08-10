# Persistent storage for the three directories the app currently resolves
# to local (ephemeral-on-Fargate) disk:
#   backend/app/services/faiss_vector_store.py -> /app/vector_store
#   backend/app/services/upload_service.py     -> /app/uploads
#   backend/app/services/feedback_service.py   -> /app/feedback
#
# One EFS filesystem, three access points — mirrors docker-compose.yml's
# existing named-volume pattern for local dev (backend_uploads,
# backend_vector_store), extended to also cover /app/feedback, which isn't
# even volume-mounted locally today. This is the first time feedback data
# is persisted outside a single container's local disk.

resource "aws_efs_file_system" "app_data" {
  creation_token = "${var.project_name}-app-data"
  encrypted      = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = {
    Name = "${var.project_name}-app-data"
  }
}

resource "aws_efs_mount_target" "app_data" {
  for_each = aws_subnet.public

  file_system_id  = aws_efs_file_system.app_data.id
  subnet_id       = each.value.id
  security_groups = [aws_security_group.efs.id]
}

# owner_uid/gid = 1000 assumes `useradd --create-home --shell /usr/sbin/nologin
# appuser` in backend/Dockerfile gets the first free UID on python:3.11-slim
# (typically 1000). MUST be verified against the actual built image before
# applying — see infra/README.md Step 2 (`docker run --rm <image> id appuser`).
# If it differs, update owner_uid/owner_gid/posix_user below to match, or the
# container won't be able to write to its mounted EFS directories.
locals {
  efs_owner_uid = 1000
  efs_owner_gid = 1000
}

resource "aws_efs_access_point" "uploads" {
  file_system_id = aws_efs_file_system.app_data.id

  posix_user {
    uid = local.efs_owner_uid
    gid = local.efs_owner_gid
  }

  root_directory {
    path = "/uploads"
    creation_info {
      owner_uid   = local.efs_owner_uid
      owner_gid   = local.efs_owner_gid
      permissions = "0755"
    }
  }

  tags = { Name = "${var.project_name}-uploads" }
}

resource "aws_efs_access_point" "vector_store" {
  file_system_id = aws_efs_file_system.app_data.id

  posix_user {
    uid = local.efs_owner_uid
    gid = local.efs_owner_gid
  }

  root_directory {
    path = "/vector_store"
    creation_info {
      owner_uid   = local.efs_owner_uid
      owner_gid   = local.efs_owner_gid
      permissions = "0755"
    }
  }

  tags = { Name = "${var.project_name}-vector-store" }
}

resource "aws_efs_access_point" "feedback" {
  file_system_id = aws_efs_file_system.app_data.id

  posix_user {
    uid = local.efs_owner_uid
    gid = local.efs_owner_gid
  }

  root_directory {
    path = "/feedback"
    creation_info {
      owner_uid   = local.efs_owner_uid
      owner_gid   = local.efs_owner_gid
      permissions = "0755"
    }
  }

  tags = { Name = "${var.project_name}-feedback" }
}
