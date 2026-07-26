terraform {
  required_version = ">= 1.5.0"

  # Documented backend for real plans/applies (out of band). CI uses -backend=false.
  # Copy backends/ci.local.hcl.example → backends/ci.local.hcl and pass:
  #   terraform init -backend-config=backends/ci.local.hcl
  backend "local" {
    path = "terraform.tfstate"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40.0, < 6.0.0"
    }
  }
}

# CI / offline plan: mock credentials (no live AWS calls with -refresh=false).
provider "aws" {
  region                      = var.aws_region
  access_key                  = var.aws_access_key
  secret_key                  = var.aws_secret_key
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}
