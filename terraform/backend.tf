terraform {
  backend "s3" {
    bucket  = "predictive-llm-k8s-tfstate-655748577231"
    key     = "envs/dev/terraform.tfstate"
    region  = "eu-central-1"
    encrypt = true
  }
}
