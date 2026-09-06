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
# Static External Public IP (Guarantees IP remains unchanged across reboots)
# ------------------------------------------------------------------------------
resource "google_compute_address" "static_ip" {
  name   = "${var.instance_name}-ip"
  region = var.region
}

# ------------------------------------------------------------------------------
# Firewall Rules: Allow Inbound SSH (22) and Web Terminal (e.g. 8000)
# ------------------------------------------------------------------------------
resource "google_compute_firewall" "allow_app_and_ssh" {
  name    = "${var.instance_name}-firewall"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22", tostring(var.app_port)]
  }

  source_ranges = var.allowed_ingress_cidrs
  target_tags   = ["nse-trading-server"]
}

# ------------------------------------------------------------------------------
# Compute Engine VM Instance
# ------------------------------------------------------------------------------
resource "google_compute_instance" "trading_vm" {
  name         = var.instance_name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["nse-trading-server", "http-server"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.boot_disk_size_gb
      type  = var.boot_disk_type
    }
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.static_ip.address
    }
  }

  # Automated Startup Script: Provisions Swapfile, Docker & Docker Compose
  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -euo pipefail

    echo "=== [1/5] Configuring 2 GB Swap Space for Memory Stability ==="
    if [ ! -f /swapfile ]; then
      fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
      chmod 600 /swapfile
      mkswap /swapfile
      swapon /swapfile
      echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi

    echo "=== [2/5] Updating system packages ==="
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg lsb-release git

    echo "=== [3/5] Installing official Docker & Compose plugin ==="
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    systemctl enable docker
    systemctl start docker

    echo "=== [4/5] Preparing application workspace ==="
    mkdir -p /opt/nse_trading_terminal/data
    chmod -R 777 /opt/nse_trading_terminal/data

    echo "=== [5/5] Provisioning completed successfully! ==="
  EOF

  resource_policies = var.enable_schedule ? [google_compute_resource_policy.market_schedule[0].id] : []

  service_account {
    scopes = ["cloud-platform"]
  }
}

# ------------------------------------------------------------------------------
# Automated Market Hours Schedule (Optional: Auto Start & Stop VM)
# ------------------------------------------------------------------------------
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_compute_resource_policy" "market_schedule" {
  count  = var.enable_schedule ? 1 : 0
  name   = "${var.instance_name}-market-schedule"
  region = var.region

  instance_schedule_policy {
    vm_start_schedule {
      schedule = var.schedule_start
    }
    vm_stop_schedule {
      schedule = var.schedule_stop
    }
    time_zone = var.schedule_timezone
  }
}

resource "google_project_iam_member" "compute_admin_schedule" {
  count   = var.enable_schedule ? 1 : 0
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:service-${data.google_project.current.number}@compute-system.iam.gserviceaccount.com"
}


