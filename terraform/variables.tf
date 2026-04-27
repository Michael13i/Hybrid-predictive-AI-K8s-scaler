variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "predictive-llm-k8s"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

#Networking (VPC, Subnets)

variable "vpc_cidr" {
  description = "CIDR for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_a_cidr" {
  description = "CIDR for public subnet A"
  type        = string
  default     = "10.0.1.0/24"
}

variable "public_subnet_b_cidr" {
  description = "CIDR for public subnet B"
  type        = string
  default     = "10.0.2.0/24"
}

#Ollama EC2

variable "ollama_instance_type" {
  description = "EC2 instance type for Ollama"
  type        = string
  default     = "t3.large"
}

variable "ollama_allowed_cidr" {
  description = "CIDR allowed to SSH"
  type        = string
  default     = "0.0.0.0/0"
}

variable "ssh_key_name" {
  description = "EC2 key pair name"
  type        = string
  default     = "mike-key-Frankfurt"
}

#EKS Cluster

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "predictive-llm-k8s-cluster"
}

variable "cluster_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.31"
}

#EKS Node Group

variable "node_instance_type" {
  description = "Instance type for EKS worker nodes"
  type        = string
  default     = "t3.large"
}

variable "node_desired_size" {
  description = "Desired node group size"
  type        = number
  default     = 1
}

variable "node_min_size" {
  description = "Minimum node group size"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum node group size"
  type        = number
  default     = 1
}
