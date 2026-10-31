variable "vpc_id" {
  description = "SG를 만들 VPC id"
  type        = string
}

variable "my_ip" {
  description = "ssh - grafana 접속을 허용할 IP"
  type        = string
}
