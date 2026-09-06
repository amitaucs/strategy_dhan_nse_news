output "vm_public_ip" {
  description = "Public IP of the GCP VM running ST15_LargeCap."
  value       = data.google_compute_instance.target_vm.network_interface[0].access_config[0].nat_ip
}

output "st15_url" {
  description = "Direct URL for ST15_LargeCap Web UI."
  value       = "http://${data.google_compute_instance.target_vm.network_interface[0].access_config[0].nat_ip}:${var.app_port}"
}

