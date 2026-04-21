data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["137112412989"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_security_group" "ollama" {
  name   = "${var.project_name}-ollama-sg"
  vpc_id = aws_vpc.main.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ollama_allowed_cidr]
  }

  ingress {
    description = "Ollama API from VPC"
    from_port   = 11434
    to_port     = 11434
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-ollama-sg"
  })
}

resource "aws_instance" "ollama" {
  ami                         = data.aws_ami.amazon_linux_2023.id
  instance_type               = var.ollama_instance_type
  subnet_id                   = aws_subnet.public_a.id
  vpc_security_group_ids      = [aws_security_group.ollama.id]
  key_name                    = var.ssh_key_name
  associate_public_ip_address = true

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  user_data_replace_on_change = true

  user_data = <<-EOF
              #!/bin/bash
              set -euxo pipefail

              dnf update -y
              dnf install -y cloud-utils-growpart xfsprogs

              growpart /dev/nvme0n1 1 || true
              xfs_growfs -d / || true

              curl -fsSL https://ollama.com/install.sh | sh

              useradd -r -s /bin/false -U -m -d /usr/share/ollama ollama || true
              usermod -a -G ollama ec2-user || true

              cat >/etc/systemd/system/ollama.service <<'EOT'
              [Unit]
              Description=Ollama Service
              After=network-online.target

              [Service]
              ExecStart=/usr/local/bin/ollama serve
              User=ollama
              Group=ollama
              Restart=always
              RestartSec=3
              Environment="OLLAMA_HOST=0.0.0.0:11434"
              Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

              [Install]
              WantedBy=multi-user.target
              EOT

              systemctl daemon-reload
              systemctl enable ollama
              systemctl start ollama

              sleep 20
              su - ec2-user -c "ollama pull llama2:7b" || true
              EOF

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-ollama"
  })
}
