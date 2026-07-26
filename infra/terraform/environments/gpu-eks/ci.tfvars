# Documented CI / offline plan inputs (mock IDs — not a real cluster).
# terraform plan -var-file=ci.tfvars -refresh=false
# Real applies: copy to a private tfvars (gitignored) with real subnet/role ARNs.

aws_region     = "us-east-1"
cluster_name   = "vulcan-ci-mock"
subnet_ids     = ["subnet-00000000000000001", "subnet-00000000000000002"]
node_role_arn  = "arn:aws:iam::123456789012:role/vulcan-eks-gpu-node"
tags = {
  Environment = "ci-mock"
}
