# Karpenter GPU NodePool policies (ADR-005 / phase 7–8 label alignment).
package vulcan.karpenter

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
	input.kind == "NodePool"
	not input.metadata.labels["vulcan.dev/component"] == "karpenter"
	msg := sprintf("NodePool %s must be labeled vulcan.dev/component=karpenter", [input.metadata.name])
}

deny contains msg if {
	input.kind == "NodePool"
	not input.spec.disruption.consolidationPolicy
	msg := sprintf("NodePool %s must set disruption.consolidationPolicy", [input.metadata.name])
}

deny contains msg if {
	input.kind == "NodePool"
	not input.spec.disruption.budgets
	msg := sprintf("NodePool %s must set disruption.budgets (spot drain safety)", [input.metadata.name])
}

deny contains msg if {
	input.kind == "NodePool"
	labels := input.spec.template.metadata.labels
	labels["vulcan.dev/gpu"] != "true"
	msg := sprintf("NodePool %s must set vulcan.dev/gpu=true (phase 7/8 flavors)", [input.metadata.name])
}

deny contains msg if {
	input.kind == "NodePool"
	not has_gpu_taint(input)
	msg := sprintf("NodePool %s must taint nvidia.com/gpu=true:NoSchedule", [input.metadata.name])
}

deny contains msg if {
	input.kind == "NodePool"
	input.metadata.name == "vulcan-gpu-mig-small"
	input.spec.template.metadata.labels["nvidia.com/mig.config"] != "many-small-inference"
	msg := "mig-small NodePool must use nvidia.com/mig.config=many-small-inference"
}

deny contains msg if {
	input.kind == "NodePool"
	input.metadata.name == "vulcan-gpu-mig-large"
	input.spec.template.metadata.labels["nvidia.com/mig.config"] != "training-large-batch"
	msg := "mig-large NodePool must use nvidia.com/mig.config=training-large-batch"
}

deny contains msg if {
	input.kind == "EC2NodeClass"
	not input.metadata.labels["app.kubernetes.io/part-of"] == "vulcan"
	msg := "EC2NodeClass must be labeled app.kubernetes.io/part-of=vulcan"
}

has_gpu_taint(np) if {
	some t in np.spec.template.spec.taints
	t.key == "nvidia.com/gpu"
	t.effect == "NoSchedule"
}
