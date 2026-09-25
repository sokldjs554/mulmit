# Runtime identity for the API, worker and migration job.
resource "google_service_account" "runtime" {
  account_id   = "mulmit-runtime"
  display_name = "mulmit API / worker / migrations"
}

# The web server only proxies to the API; it needs no Google API permissions.
resource "google_service_account" "web" {
  account_id   = "mulmit-web"
  display_name = "mulmit web (Next.js)"
}

# GitHub Actions deploys as this account through Workload Identity Federation (wif.tf).
resource "google_service_account" "deployer" {
  account_id   = "mulmit-deployer"
  display_name = "GitHub Actions deployer"
}

resource "google_project_iam_member" "runtime" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_storage_bucket_iam_member" "runtime_raw" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

# Deploying a revision "as" a runtime identity requires actAs on it.
resource "google_service_account_iam_member" "deployer_act_as" {
  for_each = {
    runtime = google_service_account.runtime.name
    web     = google_service_account.web.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
