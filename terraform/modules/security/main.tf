resource "aws_security_group" "web" {
  name   = "web-sg"
  vpc_id = var.vpc_id

  tags = {
    Name = "web-sg"
  }
}

resource "aws_security_group" "db" {
  name   = "db-sg"
  vpc_id = var.vpc_id

  tags = {
    Name = "db-sg"
  }
}

resource "aws_security_group" "monitoring" {
    name = "monitoring-sg"
    vpc_id = var.vpc_id

    tags = {
      Name = "monitoring-sg"
    }
}

#DB 규칙
resource "aws_vpc_security_group_ingress_rule" "db_from_web_5432" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "db_from_web_22" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 22
  to_port                      = 22
}

resource "aws_vpc_security_group_ingress_rule" "db_from_monitoring_5432" {
  security_group_id = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol = "tcp"
  from_port = 5432
  to_port = 5432
}

resource "aws_vpc_security_group_ingress_rule" "db_from_monitoring_9100" {
  security_group_id = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol = "tcp"
  from_port = 9100
  to_port = 9100
}
#web 규칙
resource "aws_vpc_security_group_ingress_rule" "web_from_http_80" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "web_ssh_22" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = var.my_ip
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_ingress_rule" "web_from_monitoring_80" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_ingress_rule" "web_from_monitoring_8000" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_ingress_rule" "web_from_monitoring_9100" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol                  = "tcp"
  from_port                    = 9100
  to_port                      = 9100
}

#monitoring 규칙

resource "aws_vpc_security_group_ingress_rule" "monitoring_grafana" {
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4 = var.my_ip
  ip_protocol = "tcp"
  from_port = 3000
  to_port = 3000
}

resource "aws_vpc_security_group_ingress_rule" "monitoring_ssh" {
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4 = var.my_ip
  ip_protocol = "tcp"
  from_port = 22
  to_port = 22
}