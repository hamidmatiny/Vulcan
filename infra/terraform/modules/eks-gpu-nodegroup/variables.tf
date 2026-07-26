variable "cluster_name" {
  description = "Existing EKS cluster name"
  type        = string
}

variable "node_group_name" {
  description = "EKS managed node group name"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for the GPU node group"
  type        = list(string)
}

variable "node_role_arn" {
  description = "IAM role ARN for the node group"
  type        = string
}

variable "instance_types" {
  description = "GPU instance types (EKS)"
  type        = list(string)
  default     = ["g5.xlarge"]
}

variable "ami_type" {
  description = "EKS AMI type with NVIDIA drivers"
  type        = string
  default     = "AL2_x86_64_GPU"
}

variable "desired_size" {
  type    = number
  default = 0
}

variable "min_size" {
  type    = number
  default = 0
}

variable "max_size" {
  type    = number
  default = 2
}

variable "disk_size" {
  type    = number
  default = 100
}

variable "mig_profile" {
  description = "Default nvidia.com/mig.config label value for nodes in this group"
  type        = string
  default     = "all-disabled"
}

variable "capacity_type" {
  type    = string
  default = "ON_DEMAND"
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "tags" {
  type    = map(string)
  default = {}
}
