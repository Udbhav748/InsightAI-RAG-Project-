# Public-subnets-only VPC — deliberately no NAT Gateway.
#
# Fargate tasks are placed in public subnets with a public IP assigned
# directly, so they can reach the internet (Gemini/Groq APIs, the research
# agent's web search) without a NAT Gateway, which costs ~$32/month base
# plus data processing regardless of traffic volume. That's a meaningful
# cost for a portfolio-scale deployment.
#
# This is a cost trade-off, not a security compromise: having a public IP
# does not mean the task is reachable from the internet on its application
# port. security_groups.tf locks ingress on the task's security group down
# to the ALB's security group only, and the ALB itself only accepts traffic
# from CloudFront's origin-facing IP range. Two public subnets (not one) are
# required regardless, since an ALB must span at least two AZs.

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_subnet" "public" {
  for_each = {
    a = { cidr = "10.0.1.0/24", az_index = 0 }
    b = { cidr = "10.0.2.0/24", az_index = 1 }
  }

  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value.cidr
  availability_zone       = data.aws_availability_zones.available.names[each.value.az_index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-${each.key}"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}
