# Policies for Vulcan GPU Operator values + MIG ConfigMaps (ADR-002 / ADR-003).
package vulcan.gpu_infra

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# --- ConfigMaps we render ---

deny contains msg if {
	input.kind == "ConfigMap"
	input.metadata.labels["vulcan.dev/component"] == "mig-parted"
	not contains(input.data["config.yaml"], "many-small-inference")
	msg := "MIG ConfigMap must define many-small-inference profile (ADR-003)"
}

deny contains msg if {
	input.kind == "ConfigMap"
	input.metadata.labels["vulcan.dev/component"] == "mig-parted"
	not contains(input.data["config.yaml"], "training-large-batch")
	msg := "MIG ConfigMap must define training-large-batch profile (ADR-003)"
}

deny contains msg if {
	input.kind == "ConfigMap"
	input.metadata.labels["vulcan.dev/component"] == "mig-parted"
	not contains(input.data["config.yaml"], "1g.5gb")
	msg := "many-small-inference profile must include 1g.5gb slices"
}

deny contains msg if {
	input.kind == "ConfigMap"
	input.metadata.labels["vulcan.dev/component"] == "device-plugin"
	not input.metadata.labels["vulcan.dev/layer"] == "device-plugin"
	msg := "device plugin ConfigMap must be labeled vulcan.dev/layer=device-plugin"
}

deny contains msg if {
	input.kind == "ConfigMap"
	input.metadata.labels["vulcan.dev/component"] == "device-plugin"
	not input.data["mig-mixed"]
	msg := "device plugin ConfigMap must include mig-mixed entry"
}

deny contains msg if {
	input.kind == "Namespace"
	input.metadata.name == "gpu-operator"
	input.metadata.labels["app.kubernetes.io/part-of"] != "vulcan"
	msg := "gpu-operator namespace must be labeled app.kubernetes.io/part-of=vulcan"
}

# Forbid GPU resource requests on Vulcan overlay ConfigMaps (they are not workloads).
deny contains msg if {
	input.kind == "ConfigMap"
	input.metadata.labels["app.kubernetes.io/part-of"] == "vulcan"
	input.data["nvidia.com/gpu"]
	msg := sprintf("ConfigMap %s must not embed nvidia.com/gpu resource requests", [input.metadata.name])
}
