variable "vpc_cidr" {
  description = "vpc 대역"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "public subnet 대역"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "private subnet 대역"
  type        = string
  default     = "10.0.2.0/24"
}

variable "az" {
  description = "가용 영역"
  type        = string
  default     = "ap-northeast-2a"
}

variable "enable_nat" {
  type    = bool
  default = false
}

variable "my_ip" {
  description = "ssh - grafana 접속을 허용할 IP"
  type        = string
}