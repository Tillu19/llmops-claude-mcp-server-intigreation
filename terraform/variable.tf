variable "region" {
  default = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the custom VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_1_cidr" {
  description = "CIDR block for the first public subnet."
  type        = string
  default     = "10.0.1.0/24"
}

variable "public_subnet_2_cidr" {
  description = "CIDR block for the second public subnet."
  type        = string
  default     = "10.0.2.0/24"
}

variable "private_subnet_1_cidr" {
  description = "CIDR block for the first private subnet."
  type        = string
  default     = "10.0.101.0/24"
}

variable "private_subnet_2_cidr" {
  description = "CIDR block for the second private subnet."
  type        = string
  default     = "10.0.102.0/24"
}

variable "instance_type" {
  description = "EC2 instance type for the demo servers."
  type        = string
  default     = "t2.micro"
}

variable "key_name" {
  description = "ec2_key name"
  type        = string
  default = "us-east-1"
}


variable "az1" {
  type = string
  default = "us-east-1a"
  
}

variable "az2" {
  type = string
  default = "us-east-1b"  
  
}
variable "ami" {
  description = "amiid"
type = string
default = "ami-0ea87431b78a82070"
}
