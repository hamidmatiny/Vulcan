variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_access_key" {
  type        = string
  default     = "mock"
  description = "CI uses mock keys; real applies use env/instance credentials via backend override"
}

variable "aws_secret_key" {
  type        = string
  default     = "mock"
  sensitive   = true
  description = "CI uses mock keys; never commit real secrets"
}

variable "cluster_name" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "node_role_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
