variable "vpc_cidr" {
    description = "vpc 대역"
    type = string
    default = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
    description = "public subnet 대역"
    type = string
    default = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
    description = "private subnet 대역"
    type = string
    default = "10.0.2.0/24"
}

variable "az" {
    description = "가용 영역"
    type = string
    default = "ap-northeast-2a"
}

resource "aws_vpc" "main" {
    cidr_block = var.vpc_cidr
    enable_dns_support = true
    enable_dns_hostnames = true

    tags = {
        Name = "main-vpc"
    }
}

data "aws_availability_zones" "available" {
    state = "available"
}

resource "aws_subnet" "public_subnet" {
    vpc_id = aws_vpc.main.id
    cidr_block = var.public_subnet_cidr
    availability_zone = var.az

    tags = {
      Name = "public-subnet"
    }
}

resource "aws_subnet" "private_subnet" {
    vpc_id = aws_vpc.main.id
    cidr_block = var.private_subnet_cidr
    availability_zone = var.az

    tags = {
      Name = "private-subnet"
    }
}