package vulcan.gpu_infra_test

import data.vulcan.gpu_infra
import future.keywords.if
import future.keywords.in

test_mig_requires_both_profiles if {
	doc := {
		"kind": "ConfigMap",
		"metadata": {
			"name": "vulcan-mig-parted-configs",
			"labels": {
				"app.kubernetes.io/part-of": "vulcan",
				"vulcan.dev/component": "mig-parted",
			},
		},
		"data": {"config.yaml": "version: v1\nmig-configs:\n  many-small-inference:\n    - mig-devices:\n        \"1g.5gb\": 7\n  training-large-batch:\n    - mig-devices:\n        \"3g.40gb\": 1\n"},
	}
	count(gpu_infra.deny) == 0 with input as doc
}

test_mig_deny_missing_small if {
	doc := {
		"kind": "ConfigMap",
		"metadata": {
			"name": "vulcan-mig-parted-configs",
			"labels": {
				"app.kubernetes.io/part-of": "vulcan",
				"vulcan.dev/component": "mig-parted",
			},
		},
		"data": {"config.yaml": "training-large-batch: only"},
	}
	some msg in gpu_infra.deny with input as doc
	contains(msg, "many-small-inference")
}
