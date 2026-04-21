output "aws_region" {
  value = var.aws_region
}

output "ecr_repository_url" {
  value = aws_ecr_repository.scaler.repository_url
}
output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_a_id" {
  value = aws_subnet.public_a.id
}

output "public_subnet_b_id" {
  value = aws_subnet.public_b.id
}

output "ollama_public_ip" {
  value = aws_instance.ollama.public_ip
}

output "ollama_private_ip" {
  value = aws_instance.ollama.private_ip
}
