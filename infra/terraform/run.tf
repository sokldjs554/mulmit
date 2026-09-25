# Cloud Run: api (internal ingress), worker (always-on CPU, one instance), web (public),
# and the migration job. Terraform owns configuration; the deploy workflow owns images (and
# the worker/job commands, which the placeholder image could not run), hence ignore_changes.

locals {
  runtime_env = {
    MULMIT_ENV                = "production"
    MULMIT_LOG_JSON           = "true"
    MULMIT_STORAGE_URL        = "gs://${google_storage_bucket.raw.name}/raw"
    MULMIT_PUBLIC_WEB_URL     = var.web_url
    MULMIT_CORS_ORIGINS       = jsonencode(var.web_url == "" ? [] : [var.web_url])
    MULMIT_COOKIE_SECURE      = "true"
    MULMIT_LLM_PROVIDER       = var.llm_provider
    MULMIT_PAYMENT_PROVIDER   = var.payment_provider
    MULMIT_TOSS_CLIENT_KEY    = var.toss_client_key
    MULMIT_EMBEDDING_PROVIDER = contains(keys(var.mounted_external_secrets), "MULMIT_VOYAGE_API_KEY") ? "voyage" : "hashing"
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = "mulmit-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY" # reachable from the web service, not the internet
  deletion_protection = false

  template {
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 40

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = 10
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
      egress = "PRIVATE_RANGES_ONLY" # SQL/Redis over VPC; public APIs (data.go.kr, Claude) direct
    }

    containers {
      image = local.placeholder_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.runtime_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.runtime_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        tcp_socket {
          port = 8000
        }
        period_seconds    = 3
        failure_threshold = 20
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds = 30
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_secret_manager_secret_version.generated,
    google_secret_manager_secret_iam_member.runtime_generated,
    google_secret_manager_secret_iam_member.runtime_external,
  ]
}

resource "google_cloud_run_v2_service" "worker" {
  name                = "mulmit-worker"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    service_account = google_service_account.runtime.email

    # Exactly one always-on instance: arq pulls from Redis and runs cron itself, so there is
    # no request to wake it up (ADR-0003).
    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = local.placeholder_image

      ports {
        container_port = 8080 # `mulmit worker` serves /healthz here
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi" # OCR renders 300dpi pages
        }
        cpu_idle = false
      }

      dynamic "env" {
        for_each = local.runtime_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.runtime_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        tcp_socket {
          port = 8080
        }
        period_seconds    = 5
        failure_threshold = 24
      }

      # 503 once arq's Redis heartbeat goes stale: a wedged worker gets replaced.
      liveness_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds    = 60
        failure_threshold = 3
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].containers[0].command,
      template[0].containers[0].args,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_secret_manager_secret_version.generated,
    google_secret_manager_secret_iam_member.runtime_generated,
    google_secret_manager_secret_iam_member.runtime_external,
  ]
}

resource "google_cloud_run_v2_job" "migrate" {
  name                = "mulmit-migrate"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1

    template {
      service_account = google_service_account.runtime.email
      max_retries     = 0
      timeout         = "600s"

      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = local.placeholder_image

        dynamic "env" {
          for_each = local.runtime_env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = local.generated_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      template[0].template[0].containers[0].command,
      template[0].template[0].containers[0].args,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_version.generated]
}

resource "google_cloud_run_v2_service" "web" {
  name                = "mulmit-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.web.email

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    # All egress through the VPC so calls to the internal-only API count as internal traffic
    # (run.app is reached via Private Google Access on the subnet). The web server talks to
    # nothing else; browser-side scripts load from the user's network.
    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
      egress = "ALL_TRAFFIC"
    }

    containers {
      image = local.placeholder_image

      ports {
        container_port = 3000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "API_ORIGIN"
        value = google_cloud_run_v2_service.api.uri
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# Network position (internal ingress) is the API's gate; the web service is public.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = {
    web = google_cloud_run_v2_service.web.name
    api = google_cloud_run_v2_service.api.name
  }
  location = var.region
  name     = each.value
  role     = "roles/run.invoker"
  member   = "allUsers"
}
