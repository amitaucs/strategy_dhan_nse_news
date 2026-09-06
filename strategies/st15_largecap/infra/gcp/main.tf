terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ------------------------------------------------------------------------------
# Lookup Existing Shared VM
# ------------------------------------------------------------------------------
data "google_compute_instance" "target_vm" {
  name = var.instance_name
  zone = var.zone
}

# ------------------------------------------------------------------------------
# Firewall Rule: Allow Port 8015 for ST15_LargeCap
# ------------------------------------------------------------------------------
resource "google_compute_firewall" "allow_st15_port" {
  name    = "${var.instance_name}-st15-firewall"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = [tostring(var.app_port)]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = data.google_compute_instance.target_vm.tags
}

