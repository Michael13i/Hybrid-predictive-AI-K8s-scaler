resource "local_file" "scaler_configmap_rendered" {
  content = templatefile("${path.module}/../k8s/aws/scaler-configmap.yaml.tpl", {
    ollama_private_ip = aws_instance.ollama.private_ip
  })

  filename = "${path.module}/../k8s/generated/scaler-configmap.yaml"
}
