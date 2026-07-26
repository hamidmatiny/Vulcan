package vulcan.kubeflow.handoff_test

import data.vulcan.kubeflow.handoff
import future.keywords.if

test_allow_phase6_shaped_isvc if {
	doc := {
		"kind": "InferenceService",
		"metadata": {
			"name": "vulcan-vllm-finetuned",
			"labels": {
				"app.kubernetes.io/part-of": "vulcan",
				"vulcan.dev/backend": "vllm",
				"vulcan.dev/model_id": "reference-tiny-llm",
			},
			"annotations": {"serving.kserve.io/deploymentMode": "RawDeployment"},
		},
	}
	count(handoff.deny) == 0 with input as doc
}
