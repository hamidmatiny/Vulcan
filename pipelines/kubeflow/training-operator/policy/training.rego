# PyTorchJob must compose phase-8 Kueue + phase-9 Karpenter/checkpointing.
package vulcan.kubeflow.training

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
	input.kind == "PyTorchJob"
	not input.metadata.labels["kueue.x-k8s.io/queue-name"] == "lq-training"
	msg := sprintf("PyTorchJob %s must label kueue.x-k8s.io/queue-name=lq-training", [input.metadata.name])
}

deny contains msg if {
	input.kind == "PyTorchJob"
	not input.metadata.labels["vulcan.dev/model_id"] == "reference-tiny-llm"
	msg := sprintf("PyTorchJob %s must target reference-tiny-llm", [input.metadata.name])
}

deny contains msg if {
	input.kind == "PyTorchJob"
	spec := input.spec.pytorchReplicaSpecs.Master.template.spec
	spec.nodeSelector["vulcan.dev/gpu-pool"] != "mig-large"
	msg := sprintf("PyTorchJob %s must nodeSelect vulcan.dev/gpu-pool=mig-large (Karpenter)", [input.metadata.name])
}

deny contains msg if {
	input.kind == "PyTorchJob"
	not has_gpu_toleration(input)
	msg := sprintf("PyTorchJob %s must tolerate nvidia.com/gpu", [input.metadata.name])
}

deny contains msg if {
	input.kind == "PyTorchJob"
	not uses_checkpoint_command(input)
	msg := sprintf("PyTorchJob %s must run vulcan-checkpoint-finetune (phase-9)", [input.metadata.name])
}

has_gpu_toleration(job) if {
	some t in job.spec.pytorchReplicaSpecs.Master.template.spec.tolerations
	t.key == "nvidia.com/gpu"
}

uses_checkpoint_command(job) if {
	cmd := job.spec.pytorchReplicaSpecs.Master.template.spec.containers[0].command
	some c in cmd
	c == "vulcan-checkpoint-finetune"
}
