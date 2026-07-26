package vulcan.karpenter_test

import data.vulcan.karpenter
import future.keywords.if
import future.keywords.in

test_nodepool_requires_budgets if {
	doc := {
		"kind": "NodePool",
		"metadata": {"name": "x", "labels": {"vulcan.dev/component": "karpenter"}},
		"spec": {
			"disruption": {"consolidationPolicy": "WhenEmptyOrUnderutilized"},
			"template": {
				"metadata": {"labels": {"vulcan.dev/gpu": "true"}},
				"spec": {"taints": [{"key": "nvidia.com/gpu", "effect": "NoSchedule"}]},
			},
		},
	}
	some msg in karpenter.deny with input as doc
	contains(msg, "disruption.budgets")
}

test_allow_valid_nodepool if {
	doc := {
		"kind": "NodePool",
		"metadata": {"name": "vulcan-gpu-mig-small", "labels": {"vulcan.dev/component": "karpenter"}},
		"spec": {
			"disruption": {
				"consolidationPolicy": "WhenEmptyOrUnderutilized",
				"budgets": [{"nodes": "20%"}],
			},
			"template": {
				"metadata": {"labels": {
					"vulcan.dev/gpu": "true",
					"nvidia.com/mig.config": "many-small-inference",
				}},
				"spec": {"taints": [{"key": "nvidia.com/gpu", "effect": "NoSchedule"}]},
			},
		},
	}
	count(karpenter.deny) == 0 with input as doc
}
