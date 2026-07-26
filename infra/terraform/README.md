# infra/terraform

Terraform for Vulcan cloud foundation pieces used by GPU scheduling. **CI runs `validate` + `plan` only — never `apply`** ([ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md)).

## Layout

```text
environments/gpu-eks/     EKS GPU managed node groups (inference + MIG pools)
modules/eks-gpu-nodegroup/ Reusable node group (labels, taints, instance types)
```

## GPU node groups (phase 7)

| Module instance | Instance types | Default MIG label | Intent |
|-----------------|----------------|-------------------|--------|
| `gpu_inference` | `g5.xlarge`, `g5.2xlarge` | `all-disabled` | General GPU inference |
| `gpu_mig_small` | `p4d.24xlarge` | `many-small-inference` | Triton/KServe multi-tenant |
| `gpu_mig_large` | `p4d.24xlarge` | `training-large-batch` | Large KV / batch |

All groups:

- Label `vulcan.dev/gpu=true` (GPU Operator DaemonSet nodeSelector)
- Taint `nvidia.com/gpu=true:NoSchedule`
- AMI type `AL2_x86_64_GPU` (preinstalled drivers → Operator `driver.enabled=false`)

## Backend config (documented)

Default backend in `environments/gpu-eks/versions.tf` is **local** state.

```bash
cd infra/terraform/environments/gpu-eks
terraform init -reconfigure
terraform validate
terraform plan -var-file=ci.tfvars -refresh=false
```

Default backend is **local** (`versions.tf`). Optional: `cp backends/ci.local.hcl.example backends/ci.local.hcl` and `terraform init -backend-config=backends/ci.local.hcl`.

`ci.tfvars` uses mock subnet/role ARNs for offline plan (`-refresh=false`, mock AWS keys in provider). Real applies use private tfvars (gitignored) and real AWS credentials — **manual only**.

## Validate

```bash
make validate-gpu-infra
```
