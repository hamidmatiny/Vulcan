# GPU-enabled EKS node groups for Vulcan (inference + optional large-batch).
# Instance types, labels, and taints target GPU Operator + MIG scheduling.

locals {
  common_tags = merge(
    {
      Project = "vulcan"
      Phase   = "7"
    },
    var.tags,
  )
}

# g5 / A10G-class — general inference; MIG profiles apply when hardware supports MIG
# (A100 node group below is the primary MIG target).
module "gpu_inference" {
  source = "../../modules/eks-gpu-nodegroup"

  cluster_name    = var.cluster_name
  node_group_name = "${var.cluster_name}-gpu-inference"
  subnet_ids      = var.subnet_ids
  node_role_arn   = var.node_role_arn
  instance_types  = ["g5.xlarge", "g5.2xlarge"]
  ami_type        = "AL2_x86_64_GPU"
  desired_size    = 0
  min_size        = 0
  max_size        = 4
  mig_profile     = "all-disabled"
  labels = {
    "vulcan.dev/gpu-pool" = "inference"
  }
  tags = local.common_tags
}

# p4d / A100-class — MIG many-small-inference default label for multi-tenant Triton/KServe.
module "gpu_mig_small" {
  source = "../../modules/eks-gpu-nodegroup"

  cluster_name    = var.cluster_name
  node_group_name = "${var.cluster_name}-gpu-mig-small"
  subnet_ids      = var.subnet_ids
  node_role_arn   = var.node_role_arn
  instance_types  = ["p4d.24xlarge"]
  ami_type        = "AL2_x86_64_GPU"
  desired_size    = 0
  min_size        = 0
  max_size        = 2
  mig_profile     = "many-small-inference"
  labels = {
    "vulcan.dev/gpu-pool" = "mig-small"
    "vulcan.dev/mig"      = "many-small-inference"
  }
  tags = local.common_tags
}

# A100 large partitions — training / large-batch / big vLLM KV.
module "gpu_mig_large" {
  source = "../../modules/eks-gpu-nodegroup"

  cluster_name    = var.cluster_name
  node_group_name = "${var.cluster_name}-gpu-mig-large"
  subnet_ids      = var.subnet_ids
  node_role_arn   = var.node_role_arn
  instance_types  = ["p4d.24xlarge"]
  ami_type        = "AL2_x86_64_GPU"
  desired_size    = 0
  min_size        = 0
  max_size        = 2
  mig_profile     = "training-large-batch"
  labels = {
    "vulcan.dev/gpu-pool" = "mig-large"
    "vulcan.dev/mig"      = "training-large-batch"
  }
  tags = local.common_tags
}
