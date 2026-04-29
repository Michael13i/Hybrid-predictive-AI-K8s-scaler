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
