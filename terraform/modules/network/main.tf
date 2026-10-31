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
    map_public_ip_on_launch = true #

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

resource "aws_route_table" "public_route" {
    vpc_id = aws_vpc.main.id

    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = aws_internet_gateway.igw.id
    }

    tags = {
      Name = "public-route"
    }
}

resource "aws_route_table_association" "public" {
    subnet_id = aws_subnet.public_subnet.id
    route_table_id = aws_route_table.public_route.id
}

resource "aws_eip" "nat" {
    count = var.enable_nat ? 1:0
    domain = "vpc"
}

resource "aws_internet_gateway" "igw" {
    vpc_id = aws_vpc.main.id

    tags = {
      Name = "main-igw"
    }
}

resource "aws_nat_gateway" "nat_igw" {
    count = var.enable_nat ? 1: 0
    allocation_id = aws_eip.nat[0].id
    subnet_id = aws_subnet.public_subnet.id
    depends_on = [ aws_internet_gateway.igw ]

    tags = {
      Name = "nat-gateway"
    }
}

resource "aws_route_table" "private_route" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "private-route"
  }
}

resource "aws_route_table_association" "private" {
  subnet_id = aws_subnet.private_subnet.id
  route_table_id = aws_route_table.private_route.id
}

resource "aws_route" "private_nat" {
  count = var.enable_nat ? 1:0

  route_table_id = aws_route_table.private_route.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id = aws_nat_gateway.nat_igw[0].id
}