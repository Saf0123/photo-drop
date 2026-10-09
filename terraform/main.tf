terraform {
  required_version = ">= 1.5"
  required_providers {
    google  = { source = "hashicorp/google", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}

provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

data "google_project" "this" {}

# ---------- APIs ----------
locals {
  apis = [
    "run.googleapis.com", "firestore.googleapis.com", "storage.googleapis.com",
    "artifactregistry.googleapis.com", "cloudbuild.googleapis.com", "cloudfunctions.googleapis.com",
    "eventarc.googleapis.com", "pubsub.googleapis.com", "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com", "monitoring.googleapis.com", "iam.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.key
  disable_on_destroy = false
}

# ---------- Storage: images auto-delete after 30 days ----------
resource "google_storage_bucket" "images" {
  name                        = "${var.project_id}-photo-drop-images"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced" # only the app can read; users go through Cloud Run
  force_destroy               = true

  lifecycle_rule {
    condition { age = 30 }
    action { type = "Delete" }
  }
  depends_on = [google_project_service.apis]
}

# ---------- Firestore: metadata, with a TTL policy on expires_at ----------
resource "google_firestore_database" "db" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.apis]
}

resource "google_firestore_field" "ttl" {
  database   = google_firestore_database.db.name
  collection = "images"
  field      = "expires_at"
  ttl_config {}
}

# ---------- IAM: the app gets only what it needs ----------
resource "google_service_account" "app" {
  account_id   = "photo-drop-app"
  display_name = "Photo Drop app"
}

resource "google_storage_bucket_iam_member" "app_objects" {
  bucket = google_storage_bucket.images.name
  role   = "roles/storage.objectUser" # read/write objects, cannot change bucket settings
  member = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# ---------- Cloud Run ----------
resource "google_artifact_registry_repository" "repo" {
  repository_id = "photo-drop"
  location      = var.region
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "app" {
  name                = "photo-drop"
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.app.email
    scaling {
      min_instance_count = 0 # scale to zero = no idle cost
      max_instance_count = var.max_instances
    }
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/photo-drop/app:${var.image_tag}"
      resources {
        limits = { cpu = "1", memory = "256Mi" }
      }
      env {
        name  = "BACKEND"
        value = "gcp"
      }
      env {
        name  = "BUCKET"
        value = google_storage_bucket.images.name
      }
      env {
        name  = "INVITE_CODE"
        value = var.invite_code
      }
    }
  }
  depends_on = [google_artifact_registry_repository.repo, google_firestore_database.db]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.app.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
