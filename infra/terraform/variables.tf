variable "project_id" {
  description = "GCP project that hosts everything."
  type        = string
}

variable "region" {
  description = "Seoul by default: the data sources, the customers and PIPA all point here."
  type        = string
  default     = "asia-northeast3"
}

variable "github_repository" {
  description = "owner/repo allowed to deploy through Workload Identity Federation."
  type        = string
  default     = "sokldjs554/procurement-forecast"
}

variable "web_url" {
  description = "Public URL of the web app (custom domain or the run.app URL after first apply)."
  type        = string
  default     = ""
}

variable "db_tier" {
  type    = string
  default = "db-custom-1-3840"
}

variable "db_high_availability" {
  description = "REGIONAL Cloud SQL with a standby in another zone."
  type        = bool
  default     = false
}

variable "redis_memory_gb" {
  type    = number
  default = 1
}

variable "api_min_instances" {
  description = "Keep one API instance warm to avoid cold starts on the first request."
  type        = number
  default     = 1
}

variable "llm_provider" {
  description = "anthropic once the anthropic-api-key secret has a version, heuristic before."
  type        = string
  default     = "heuristic"
}

variable "payment_provider" {
  description = "toss once the Toss secrets have versions, fake before."
  type        = string
  default     = "fake"
}

variable "mounted_external_secrets" {
  description = <<-EOT
    Operator-supplied secrets to expose to the API/worker, as ENV_NAME => secret id. Terraform
    creates every secret in local.external_secrets empty; add a version with
    `gcloud secrets versions add <id> --data-file=-`, then list it here and apply.
    Cloud Run refuses to start a revision that references a secret without a version.
  EOT
  type        = map(string)
  default     = {}
}

variable "toss_client_key" {
  description = "Toss Payments client key (public; used by the browser SDK)."
  type        = string
  default     = ""
}
