variable "project_id" {
  description = "The GCP Project ID where the strategy runs."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP compute zone."
  type        = string
  default     = "us-central1-a"
}

variable "instance_name" {
  description = "Target VM instance name (e.g. nse-trading-terminal)."
  type        = string
  default     = "nse-trading-terminal"
}

variable "app_port" {
  description = "HTTP Port for ST15_LargeCap Web UI."
  type        = number
  default     = 8015
}

variable "strategy_name" {
  description = "Identifier for the strategy."
  type        = string
  default     = "st15_largecap"
}

variable "remote_deploy_dir" {
  description = "Directory on the remote VM where this strategy is deployed."
  type        = string
  default     = "/opt/st15_largecap"
}

