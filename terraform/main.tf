module "network" {
  source = "./modules/network"

  vpc_cidr            = var.vpc_cidr
  public_subnet_cidr  = var.public_subnet_cidr
  private_subnet_cidr = var.private_subnet_cidr
  az                  = var.az
  enable_nat          = var.enable_nat
}

module "security" {
  source = "./modules/security"

  vpc_id = module.network.vpc_id
  my_ip  = var.my_ip
}

module "compute" {
  source = "./modules/compute"

  public_subnet_id  = module.network.public_subnet_id
  private_subnet_id = module.network.private_subnet_id
  web_sg_id         = module.security.web_sg_id
  monitoring_sg_id  = module.security.monitoring_sg_id
  db_sg_id          = module.security.db_sg_id
  key_name          = var.key_name
}