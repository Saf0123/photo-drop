variable "project_id" { type = string }
variable "billing_account_id" {
  type        = string
  description = "Format: XXXXXX-XXXXXX-XXXXXX"
}
variable "alert_email" { type = string }
variable "invite_code" {
  type      = string
  sensitive = true
}
variable "region" {
  type        = string
  default     = "us-central1" # Free Tier products only apply in some US regions
}
variable "budget_usd" {
  type    = number
  default = 1
}
variable "max_instances" {
  type    = number
  default = 2 # caps compute if the link gets a traffic spike
}
variable "image_tag" {
  type    = string
  default = "latest"
}
