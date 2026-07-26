output "inference_node_group_arn" {
  value = module.gpu_inference.node_group_arn
}

output "mig_small_node_group_arn" {
  value = module.gpu_mig_small.node_group_arn
}

output "mig_large_node_group_arn" {
  value = module.gpu_mig_large.node_group_arn
}
