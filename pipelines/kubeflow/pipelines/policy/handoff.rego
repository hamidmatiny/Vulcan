# InferenceService handoff must match phase-6 KServe vocabulary.
package vulcan.kubeflow.handoff

import future.keywords.contains
import future.keywords.if

deny contains msg if {
	input.kind == "InferenceService"
	not input.metadata.labels["app.kubernetes.io/part-of"] == "vulcan"
	msg := sprintf("InferenceService %s must be labeled app.kubernetes.io/part-of=vulcan", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	not input.metadata.labels["vulcan.dev/backend"] == "vllm"
	msg := sprintf("InferenceService %s handoff must use vulcan.dev/backend=vllm", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	not input.metadata.labels["vulcan.dev/model_id"] == "reference-tiny-llm"
	msg := sprintf("InferenceService %s must serve reference-tiny-llm", [input.metadata.name])
}

deny contains msg if {
	input.kind == "InferenceService"
	not input.metadata.annotations["serving.kserve.io/deploymentMode"] == "RawDeployment"
	msg := sprintf("InferenceService %s must use RawDeployment (phase-6 default)", [input.metadata.name])
}
