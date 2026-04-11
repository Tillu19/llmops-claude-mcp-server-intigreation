
resource "aws_vpc" "custom_network" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "order-assistant-vpc"
  }
}

resource "aws_internet_gateway" "custom_network_igw" {
  vpc_id = aws_vpc.custom_network.id

  tags = {
    Name = "order-assistant-igw"
  }
}

resource "aws_subnet" "public_subnet_1" {
  vpc_id                  = aws_vpc.custom_network.id
  cidr_block              = var.public_subnet_1_cidr
  availability_zone       = var.az1
  map_public_ip_on_launch = true

  tags = {
    Name = "order-assistant-public-subnet-1"
  }
}

resource "aws_subnet" "public_subnet_2" {
  vpc_id                  = aws_vpc.custom_network.id
  cidr_block              = var.public_subnet_2_cidr
  availability_zone       = var.az2
  map_public_ip_on_launch = true

  tags = {
    Name = "order-assistant-public-subnet-2"
  }
}



resource "aws_route_table" "public" {
  vpc_id = aws_vpc.custom_network.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.custom_network_igw.id
  }

  tags = {
    Name = "order-assistant-public-rt"
  }
}



resource "aws_route_table_association" "public_subnet_1" {
  subnet_id      = aws_subnet.public_subnet_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_subnet_2" {
  subnet_id      = aws_subnet.public_subnet_2.id
  route_table_id = aws_route_table.public.id
}


resource "aws_security_group" "all_traffic" {
  name        = "order-assistant-all-traffic"
  description = "Allows all inbound and outbound traffic for demo servers."
  vpc_id      = aws_vpc.custom_network.id

  ingress {
    description = "All inbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "order-assistant-all-traffic-sg"
  }
}

resource "aws_instance" "mcp_server" {
  ami                         = var.ami
  instance_type               = var.instance_type
  key_name                    = var.key_name
  subnet_id                   = aws_subnet.public_subnet_1.id
  vpc_security_group_ids      = [aws_security_group.all_traffic.id]
  associate_public_ip_address = true

  tags = {
    Name = "MCP-SERVER"
  }
}

resource "aws_instance" "web_server" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
#   key_name               = var.key_name
  subnet_id              = aws_subnet.public_subnet_2.id
  vpc_security_group_ids = [aws_security_group.all_traffic.id]
  associate_public_ip_address = true

  tags = {
    Name = "WEB-SERVER"
  }
}

