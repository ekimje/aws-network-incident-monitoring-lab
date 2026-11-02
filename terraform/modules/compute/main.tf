data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_instance" "linux_web" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.web_sg_id]
  key_name               = var.key_name

  tags = {
    Name = "linux-web"
    OS   = "linux"
  }
}

resource "aws_instance" "linux_db" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  subnet_id              = var.private_subnet_id
  vpc_security_group_ids = [var.db_sg_id]
  key_name               = var.key_name

  tags = {
    Name = "linux-db"
    OS   = "linux"
  }
}

resource "aws_instance" "linux_monitoring" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.small"
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.monitoring_sg_id]
  key_name               = var.key_name

  tags = {
    Name = "linux-monitoring"
    OS   = "linux"
  }
}