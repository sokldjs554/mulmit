locals {
  services = [
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "redis.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "sts.googleapis.com",
  ]
  # First apply runs before CI has pushed anything; the deploy workflow replaces the image and
  # Terraform ignores that field afterwards.
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"
  registry          = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "images"
  format        = "DOCKER"
  description   = "API/worker and web images"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 20
    }
  }
  cleanup_policies {
    id     = "drop-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.enabled]
}

# Raw documents (PDF/HWP/HWPX, API payloads), content-addressed by sha256.
resource "google_storage_bucket" "raw" {
  name                        = "${var.project_id}-app-raw"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}
