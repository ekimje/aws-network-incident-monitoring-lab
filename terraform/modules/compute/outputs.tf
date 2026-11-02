output "web_public_ip" {
  value = aws_instance.linux_web.public_ip
}

output "web_private_ip" {
  value = aws_instance.linux_web.private_ip
}

output "monitoring_public_ip" {
  value = aws_instance.linux_monitoring.public_ip
}

output "db_private_ip" {
  value = aws_instance.linux_db.private_ip
}