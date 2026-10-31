variable "vpc_cidr" {
    description = "vpc 대역"
    type = string
}

variable "public_subnet_cidr" {
    description = "public subnet 대역"
    type = string
}

variable "private_subnet_cidr" {
    description = "private subnet 대역"
    type = string
}

variable "az" {
    description = "가용 영역"
    type = string
}

variable "enable_nat" {
    description = "NAT 설정"
    type = bool
}
