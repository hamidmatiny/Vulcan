package vulcan.kubeflow.training_test

import data.vulcan.kubeflow.training
import future.keywords.if
import future.keywords.in

test_deny_missing_queue if {
	doc := {
		"kind": "PyTorchJob",
		"metadata": {"name": "x", "labels": {"vulcan.dev/model_id": "reference-tiny-llm"}},
		"spec": {"pytorchReplicaSpecs": {"Master": {"template": {"spec": {
			"nodeSelector": {"vulcan.dev/gpu-pool": "mig-large"},
			"tolerations": [{"key": "nvidia.com/gpu"}],
			"containers": [{"command": ["vulcan-checkpoint-finetune"]}],
		}}}}},
	}
	some msg in training.deny with input as doc
	contains(msg, "lq-training")
}

test_allow_composed_job if {
	doc := {
		"kind": "PyTorchJob",
		"metadata": {
			"name": "ok",
			"labels": {
				"kueue.x-k8s.io/queue-name": "lq-training",
				"vulcan.dev/model_id": "reference-tiny-llm",
			},
		},
		"spec": {"pytorchReplicaSpecs": {"Master": {"template": {"spec": {
			"nodeSelector": {"vulcan.dev/gpu-pool": "mig-large"},
			"tolerations": [{"key": "nvidia.com/gpu"}],
			"containers": [{"command": ["vulcan-checkpoint-finetune"]}],
		}}}}},
	}
	count(training.deny) == 0 with input as doc
}
