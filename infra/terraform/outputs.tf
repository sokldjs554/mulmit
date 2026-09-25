output "web_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "api_url" {
  description = "Internal-only; reachable from the web service."
  value       = google_cloud_run_v2_service.api.uri
}

output "artifact_registry" {
  value = local.registry
}

output "raw_bucket" {
  value = google_storage_bucket.raw.name
}

# Set these as GitHub Actions variables (Settings → Secrets and variables → Actions → Variables).
output "github_actions_variables" {
  value = {
    GCP_PROJECT_ID   = var.project_id
    GCP_REGION       = var.region
    GCP_WIF_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOY_SA    = google_service_account.deployer.email
  }
}
