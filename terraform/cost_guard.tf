# Budget -> Pub/Sub -> Cloud Run function that unlinks billing when spend passes the budget.

resource "google_pubsub_topic" "billing_alerts" {
  name       = "billing-alerts"
  depends_on = [google_project_service.apis]
}

resource "google_billing_budget" "cap" {
  billing_account = var.billing_account_id
  display_name    = "photo-drop budget"

  budget_filter {
    projects               = ["projects/${data.google_project.this.number}"]
    credit_types_treatment = "EXCLUDE_ALL_CREDITS" # track real usage cost, not cost after trial credits
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_usd)
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }

  all_updates_rule {
    pubsub_topic   = google_pubsub_topic.billing_alerts.id
    schema_version = "1.0"
  }
}

resource "google_service_account" "killswitch" {
  account_id   = "killswitch-sa"
  display_name = "Billing kill switch"
}

# Powerful role, used only by this one function.
resource "google_billing_account_iam_member" "killswitch" {
  billing_account_id = var.billing_account_id
  role               = "roles/billing.admin"
  member             = "serviceAccount:${google_service_account.killswitch.email}"
}

resource "google_storage_bucket" "src" {
  name                        = "${var.project_id}-photo-drop-src"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  force_destroy               = true
}

data "archive_file" "killswitch" {
  type        = "zip"
  source_dir  = "${path.module}/../killswitch"
  output_path = "${path.module}/killswitch.zip"
}

resource "google_storage_bucket_object" "killswitch_src" {
  name   = "killswitch-${data.archive_file.killswitch.output_md5}.zip"
  bucket = google_storage_bucket.src.name
  source = data.archive_file.killswitch.output_path
}

resource "google_cloudfunctions2_function" "killswitch" {
  name     = "stop-billing"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "stop_billing"
    source {
      storage_source {
        bucket = google_storage_bucket.src.name
        object = google_storage_bucket_object.killswitch_src.name
      }
    }
  }
  service_config {
    max_instance_count    = 1
    available_memory      = "256M"
    service_account_email = google_service_account.killswitch.email
    environment_variables = {
      GCP_PROJECT = var.project_id
      DRY_RUN     = "true" # set to "false" once you are ready to arm it
    }
  }
  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.billing_alerts.id
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }
  depends_on = [google_project_service.apis]
}
