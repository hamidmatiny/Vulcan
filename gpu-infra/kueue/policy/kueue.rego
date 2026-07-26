# Kueue multi-tenant policies (ADR-004).
package vulcan.kueue

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
	input.kind == "ClusterQueue"
	not input.metadata.labels["vulcan.dev/team"]
	msg := sprintf("ClusterQueue %s missing vulcan.dev/team label", [input.metadata.name])
}

deny contains msg if {
	input.kind == "ClusterQueue"
	not input.spec.cohort
	msg := sprintf("ClusterQueue %s must join a cohort for fair borrowing (ADR-004)", [input.metadata.name])
}

deny contains msg if {
	input.kind == "ClusterQueue"
	input.metadata.labels["vulcan.dev/team"] == "inference"
	not covers_resource(input, "nvidia.com/mig-1g.5gb")
	msg := "cq-inference must quota nvidia.com/mig-1g.5gb (ADR-003 many-small-inference)"
}

deny contains msg if {
	input.kind == "ClusterQueue"
	input.metadata.labels["vulcan.dev/team"] == "training"
	not covers_resource(input, "nvidia.com/mig-3g.40gb")
	msg := "cq-training must quota nvidia.com/mig-3g.40gb (ADR-003 training-large-batch)"
}

deny contains msg if {
	input.kind == "LocalQueue"
	not input.spec.clusterQueue
	msg := sprintf("LocalQueue %s/%s missing spec.clusterQueue", [input.metadata.namespace, input.metadata.name])
}

deny contains msg if {
	input.kind == "ResourceFlavor"
	not input.spec.tolerations
	msg := sprintf("ResourceFlavor %s must tolerate nvidia.com/gpu NoSchedule", [input.metadata.name])
}

deny contains msg if {
	input.kind == "WorkloadPriorityClass"
	not is_number(input.value)
	msg := sprintf("WorkloadPriorityClass %s must set numeric value", [input.metadata.name])
}

deny contains msg if {
	input.kind == "Workload"
	not input.spec.queueName
	msg := sprintf("Workload %s/%s missing spec.queueName", [input.metadata.namespace, input.metadata.name])
}

deny contains msg if {
	input.kind == "Workload"
	not input.spec.priorityClassName
	msg := sprintf("Workload %s/%s missing priorityClassName", [input.metadata.namespace, input.metadata.name])
}

deny contains msg if {
	input.kind == "Namespace"
	startswith(input.metadata.name, "team-")
	not input.metadata.labels["vulcan.dev/team"]
	msg := sprintf("team Namespace %s missing vulcan.dev/team", [input.metadata.name])
}

covers_resource(cq, res) if {
	some g in cq.spec.resourceGroups
	res in g.coveredResources
}
