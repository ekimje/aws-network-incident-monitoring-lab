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
  name   = "monitoring-sg"
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
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "db_from_monitoring_9100" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol                  = "tcp"
  from_port                    = 9100
  to_port                      = 9100
}

resource "aws_vpc_security_group_egress_rule" "db_to_internet_443" {
  security_group_id = aws_security_group.db.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "db_to_internet_80" {
  security_group_id = aws_security_group.db.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
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

resource "aws_vpc_security_group_egress_rule" "web_to_internet_443" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "web_to_internet_80" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "web_to_db_5432" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "web_to_db_22" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 22
  to_port                      = 22
}

#monitoring 규칙

resource "aws_vpc_security_group_ingress_rule" "monitoring_grafana" {
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4         = var.my_ip
  ip_protocol       = "tcp"
  from_port         = 3000
  to_port           = 3000
}

resource "aws_vpc_security_group_ingress_rule" "monitoring_ssh" {
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4         = var.my_ip
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_egress_rule" "monitoring_to_web_80" {
  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_egress_rule" "monitoring_to_web_8000" {
  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "monitoring_to_web_9100" {
  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 9100
  to_port                      = 9100
}

resource "aws_vpc_security_group_egress_rule" "monitoring_to_db_5432" {
  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "monitoring_to_db_9100" {
  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 9100
  to_port                      = 9100
}

resource "aws_vpc_security_group_egress_rule" "monitoring_to_internet_80" {
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "monitoring_to_internet_443" {
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}