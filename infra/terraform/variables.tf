variable "project_id" {
  description = "GCP Project ID where resources will be provisioned."
  type        = string
}

variable "region" {
  description = "GCP Region (e.g. us-central1 for 100% Free Tier, or asia-south1 for Mumbai)."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP Zone within the chosen region (e.g. us-central1-a, asia-south1-a)."
  type        = string
  default     = "us-central1-a"
}

variable "instance_name" {
  description = "Name for the Compute Engine VM instance."
  type        = string
  default     = "nse-trading-terminal"
}

variable "machine_type" {
  description = "GCE Machine Type (e2-micro is eligible for GCP Always Free in US regions)."
  type        = string
  default     = "e2-micro"
}

variable "boot_disk_size_gb" {
  description = "Size of the root boot disk in GB (up to 30 GB is included in Always Free)."
  type        = number
  default     = 30
}

variable "boot_disk_type" {
  description = "Type of boot disk (pd-standard for standard persistent disk, or pd-ssd)."
  type        = string
  default     = "pd-standard"
}

variable "app_port" {
  description = "Host port exposed for the Web GUI Dashboard."
  type        = number
  default     = 8000
}

variable "allowed_ingress_cidrs" {
  description = "CIDR blocks allowed to connect to the Web GUI (0.0.0.0/0 for public, or your specific IP/32)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ------------------------------------------------------------------------------
# Market Hours Automated Schedule (Start / Stop VM)
# ------------------------------------------------------------------------------
variable "enable_schedule" {
  description = "Enable automated VM start/stop schedule to run only during market hours."
  type        = bool
  default     = false
}

variable "schedule_timezone" {
  description = "Timezone for the schedule (e.g. Asia/Kolkata for IST)."
  type        = string
  default     = "Asia/Kolkata"
}

variable "schedule_start" {
  description = "Cron expression for VM start (e.g. '00 09 * * 1-5' for 09:00 AM IST Mon-Fri)."
  type        = string
  default     = "00 09 * * 1-5"
}

variable "schedule_stop" {
  description = "Cron expression for VM stop (e.g. '45 15 * * 1-5' for 03:45 PM IST Mon-Fri)."
  type        = string
  default     = "45 15 * * 1-5"
}

variable "strategy_name" {
  description = "Identifier for the strategy."
  type        = string
  default     = "news_based_strategy"
}

variable "remote_deploy_dir" {
  description = "Directory on the remote VM where this strategy is deployed."
  type        = string
  default     = "/opt/nse_trading_terminal"
}


