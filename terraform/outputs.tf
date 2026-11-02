output "web_public_ip" {
  value = module.compute.web_public_ip
}

output "web_private_ip" {
  value = module.compute.web_private_ip
}

output "monitoring_public_ip" {
  value = module.compute.monitoring_public_ip
}

output "db_private_ip" {
  value = module.compute.db_private_ip
}