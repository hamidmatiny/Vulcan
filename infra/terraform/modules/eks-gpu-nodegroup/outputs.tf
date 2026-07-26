output "node_group_arn" {
  value = aws_eks_node_group.gpu.arn
}

output "node_group_status" {
  value = aws_eks_node_group.gpu.status
}

output "labels" {
  value = aws_eks_node_group.gpu.labels
}
