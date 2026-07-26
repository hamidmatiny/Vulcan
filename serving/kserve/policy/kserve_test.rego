package vulcan.kserve_test

import data.vulcan.kserve
import future.keywords.if
import future.keywords.in

test_deny_missing_backend_label if {
	doc := {
		"kind": "InferenceService",
		"apiVersion": "serving.kserve.io/v1beta1",
		"metadata": {"name": "demo", "labels": {"app.kubernetes.io/part-of": "vulcan"}},
		"spec": {"predictor": {"containers": [{"name": "kserve-container", "readinessProbe": {"httpGet": {"path": "/health"}}}]}},
	}
	kserve.deny["InferenceService demo missing label vulcan.dev/backend"] with input as doc
}

test_allow_valid_isvc if {
	doc := {
		"kind": "InferenceService",
		"apiVersion": "serving.kserve.io/v1beta1",
		"metadata": {
			"name": "vulcan-triton",
			"labels": {
				"app.kubernetes.io/part-of": "vulcan",
				"vulcan.dev/backend": "triton",
			},
		},
		"spec": {
			"predictor": {
				"containers": [{
					"name": "kserve-container",
					"readinessProbe": {"httpGet": {"path": "/health"}},
					"resources": {"limits": {"cpu": "1"}},
				}],
			},
		},
	}
	count(kserve.deny) == 0 with input as doc
}

test_deny_gpu if {
	doc := {
		"kind": "InferenceService",
		"apiVersion": "serving.kserve.io/v1beta1",
		"metadata": {
			"name": "vulcan-triton",
			"labels": {
				"app.kubernetes.io/part-of": "vulcan",
				"vulcan.dev/backend": "triton",
			},
		},
		"spec": {
			"predictor": {
				"containers": [{
					"name": "kserve-container",
					"readinessProbe": {"httpGet": {"path": "/health"}},
					"resources": {"limits": {"nvidia.com/gpu": "1"}},
				}],
			},
		},
	}
	msgs := kserve.deny with input as doc
	some msg in msgs
	contains(msg, "nvidia.com/gpu")
}
