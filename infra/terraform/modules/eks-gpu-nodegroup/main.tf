# EKS managed GPU node group for Vulcan.
# Labels/taints align with gpu-infra/gpu-operator DaemonSet nodeSelector/tolerations.
# Apply out-of-band only (ADR-002) — CI runs validate/plan against documented backend.

resource "aws_eks_node_group" "gpu" {
  cluster_name    = var.cluster_name
  node_group_name = var.node_group_name
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.subnet_ids
  instance_types  = var.instance_types
  ami_type        = var.ami_type
  capacity_type   = var.capacity_type
  disk_size       = var.disk_size

  scaling_config {
    desired_size = var.desired_size
    min_size     = var.min_size
    max_size     = var.max_size
  }

  update_config {
    max_unavailable = 1
  }

  labels = merge(
    {
      "vulcan.dev/gpu"           = "true"
      "nvidia.com/gpu"           = "true"
      "nvidia.com/mig.config"    = var.mig_profile
      "vulcan.dev/workload"      = "gpu-inference"
      "node.kubernetes.io/role"  = "gpu"
    },
    var.labels,
  )

  taint {
    key    = "nvidia.com/gpu"
    value  = "true"
    effect = "NO_SCHEDULE"
  }

  tags = merge(
    {
      Name                        = var.node_group_name
      "vulcan.dev/component"      = "eks-gpu-nodegroup"
      "vulcan.dev/gpu-operator"   = "required"
    },
    var.tags,
  )

  lifecycle {
    ignore_changes = [scaling_config[0].desired_size]
  }
}
