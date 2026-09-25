locals {
  # Values Terraform can generate. They land in state: keep the state bucket locked down.
  generated_secrets = {
    "database-url"               = "postgresql+asyncpg://${google_sql_user.app.name}:${random_password.db.result}@${google_sql_database_instance.pg.private_ip_address}:5432/${google_sql_database.app.name}?ssl=require"
    "redis-url"                  = "redis://:${google_redis_instance.queue.auth_string}@${google_redis_instance.queue.host}:${google_redis_instance.queue.port}/0"
    "jwt-secret"                 = random_password.jwt.result
    "billing-key-encryption-key" = replace(replace(random_bytes.fernet.base64, "+", "-"), "/", "_")
  }
  generated_env = {
    MULMIT_DATABASE_URL               = "database-url"
    MULMIT_REDIS_URL                  = "redis-url"
    MULMIT_JWT_SECRET                 = "jwt-secret"
    MULMIT_BILLING_KEY_ENCRYPTION_KEY = "billing-key-encryption-key"
  }
  # Created empty; the operator adds versions (see var.mounted_external_secrets).
  external_secrets = toset([
    "anthropic-api-key",
    "voyage-api-key",
    "clik-api-key",
    "data-go-kr-service-key",
    "lofin-api-key",
    "toss-secret-key",
    "solapi-api-key",
    "solapi-api-secret",
    "smtp-password",
    "sentry-dsn",
  ])
  runtime_secret_env = merge(local.generated_env, var.mounted_external_secrets)
}

resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "random_bytes" "fernet" {
  length = 32
}

resource "google_secret_manager_secret" "generated" {
  for_each  = local.generated_secrets
  secret_id = each.key
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "generated" {
  for_each    = local.generated_secrets
  secret      = google_secret_manager_secret.generated[each.key].id
  secret_data = each.value
}

resource "google_secret_manager_secret" "external" {
  for_each  = local.external_secrets
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_iam_member" "runtime_generated" {
  for_each  = google_secret_manager_secret.generated
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_external" {
  for_each  = google_secret_manager_secret.external
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
