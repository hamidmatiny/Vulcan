# gpu-infra/gpu-operator

Helm **values** for the [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/) targeting **EKS GPU node groups** provisioned by [`infra/terraform`](../../infra/terraform/).

CI validates (`helm template` + conftest) and **never applies** ([ADR-002](../../docs/adr/002-gpu-cost-safety-policy.md)).

## Driver / toolkit vs device plugin

| Component | Role | Vulcan default (EKS) |
|-----------|------|----------------------|
| **driver** | Host NVIDIA driver | `enabled: false` — use EKS GPU AMI preinstalled drivers |
| **toolkit** | Container runtime hooks (`nvidia-container-toolkit`) | `enabled: true` |
| **devicePlugin** | DaemonSet advertising `nvidia.com/gpu` / MIG to kube-scheduler | Always on; config in [`values-device-plugin.yaml`](./values-device-plugin.yaml) |
| **migManager** | Applies MIG geometry from ConfigMaps + node labels | Enabled; profiles in [`../mig/`](../mig/) |

Do not conflate installing the driver with advertising devices: scheduling policy (device plugin + MIG) changes independently of the driver install path.

## Files

| File | Purpose |
|------|---------|
| [`values-eks.yaml`](./values-eks.yaml) | Base Operator values (driver/toolkit/GFD/tolerations) |
| [`values-device-plugin.yaml`](./values-device-plugin.yaml) | Device plugin ConfigMap overlay |
| [`../mig/values-mig.yaml`](../mig/values-mig.yaml) | MIG manager profiles overlay |

## Manual install (out of band)

```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo update
helm upgrade --install gpu-operator nvidia/gpu-operator \
  --version v24.9.0 \
  -n gpu-operator --create-namespace \
  -f gpu-infra/gpu-operator/values-eks.yaml \
  -f gpu-infra/gpu-operator/values-device-plugin.yaml \
  -f gpu-infra/mig/values-mig.yaml
```

Node labels/taints must match Terraform (`vulcan.dev/gpu=true`, taint `nvidia.com/gpu=true:NoSchedule`).

## Validate

```bash
make validate-gpu-infra
```
