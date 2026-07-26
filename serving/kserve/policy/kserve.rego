# Vulcan KServe policies — validate rendered InferenceService manifests (ADR-002).
package vulcan.kserve

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
	input.kind == "InferenceService"
	not input.metadata.labels["vulcan.dev/backend"]
	msg := sprintf("InferenceService %s missing label vulcan.dev/backend", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	not input.metadata.labels["app.kubernetes.io/part-of"]
	msg := sprintf("InferenceService %s missing label app.kubernetes.io/part-of", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	input.metadata.labels["app.kubernetes.io/part-of"] != "vulcan"
	msg := sprintf("InferenceService %s part-of must be vulcan", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	not startswith(input.apiVersion, "serving.kserve.io/")
	msg := sprintf("InferenceService %s must use serving.kserve.io API", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	not input.spec.predictor.containers
	msg := sprintf("InferenceService %s must define predictor.containers (custom contract adapters)", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	containers := input.spec.predictor.containers
	not main_container(containers)
	msg := sprintf("InferenceService %s missing container named kserve-container", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	some c in input.spec.predictor.containers
	c.name == "kserve-container"
	not c.readinessProbe.httpGet.path == "/health"
	msg := sprintf("InferenceService %s kserve-container readinessProbe must hit /health (contract)", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	pct := input.spec.predictor.canaryTrafficPercent
	pct != null
	not is_number(pct)
	msg := sprintf("InferenceService %s canaryTrafficPercent must be a number", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	pct := input.spec.predictor.canaryTrafficPercent
	is_number(pct)
	pct < 0
	msg := sprintf("InferenceService %s canaryTrafficPercent must be >= 0", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	pct := input.spec.predictor.canaryTrafficPercent
	is_number(pct)
	pct > 100
	msg := sprintf("InferenceService %s canaryTrafficPercent must be <= 100", [input.metadata.name])
}

# CPU-dev chart must not request nvidia.com/gpu (ADR-002).
deny contains msg if {
	input.kind == "InferenceService"
	some c in input.spec.predictor.containers
	gpu_requested(c)
	msg := sprintf(
		"InferenceService %s container %s requests nvidia.com/gpu — forbidden in CPU-dev chart (ADR-002)",
		[input.metadata.name, c.name],
	)
}

deny contains msg if {
	input.kind == "Namespace"
	input.metadata.name == "vulcan-serving"
	input.metadata.labels["vulcan.dev/role"] != "serving"
	msg := "Namespace vulcan-serving must have label vulcan.dev/role=serving"
}

main_container(containers) if {
	some c in containers
	c.name == "kserve-container"
}

gpu_requested(c) if {
	c.resources.limits["nvidia.com/gpu"]
}

gpu_requested(c) if {
	c.resources.requests["nvidia.com/gpu"]
}
