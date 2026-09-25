# PostgreSQL 16 with pgvector and pg_trgm (both supported extensions on Cloud SQL; the Alembic
# migration creates them as the cloudsqlsuperuser-member app user).
resource "google_sql_database_instance" "pg" {
  name                = "app-pg16"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = true

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = var.db_high_availability ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "18:00" # 03:00 KST
    }

    maintenance_window {
      day  = 7  # Sunday
      hour = 19 # 04:00 KST
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  depends_on = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "app" {
  name     = "app"
  instance = google_sql_database_instance.pg.name
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.pg.name
  password = random_password.db.result
}

resource "google_redis_instance" "queue" {
  name               = "app-redis"
  region             = var.region
  tier               = "BASIC"
  memory_size_gb     = var.redis_memory_gb
  redis_version      = "REDIS_7_2"
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  auth_enabled       = true

  # BASIC has no replica. Queued jobs lost on a Redis restart are recovered by the worker's
  # sweep_pending_documents cron (documents stay "pending" in PostgreSQL until processed);
  # switch to STANDARD_HA when failover matters more than cost.
  depends_on = [google_service_networking_connection.private_services]
}
