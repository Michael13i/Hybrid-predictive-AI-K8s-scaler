terraform {
  backend "s3" {
    bucket       = "predictive-llm-k8s-tfstate-655748577231"
    key          = "terraform/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
  }
}
