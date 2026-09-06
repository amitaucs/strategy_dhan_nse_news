output "instance_name" {
  description = "Name of the provisioned GCE VM instance."
  value       = google_compute_instance.trading_vm.name
}

output "instance_external_ip" {
  description = "Static Public External IP address assigned to the VM."
  value       = google_compute_address.static_ip.address
}

output "web_ui_url" {
  description = "Direct URL to access the NSE Catalyst Trading Terminal Web GUI."
  value       = "http://${google_compute_address.static_ip.address}:${var.app_port}"
}

output "ssh_command" {
  description = "gcloud CLI command to SSH into the provisioned instance."
  value       = "gcloud compute ssh ${google_compute_instance.trading_vm.name} --zone=${var.zone} --project=${var.project_id}"
}

output "deployment_instructions" {
  description = "Next steps to deploy the application onto the instance."
  value       = "Run './infra/scripts/deploy.sh' or './infra/scripts/deploy_code.sh' to sync code and launch Docker on the remote VM."
}

