package vulcan.kueue_test

import data.vulcan.kueue
import future.keywords.if
import future.keywords.in

test_inference_cq_requires_mig_1g if {
	doc := {
		"kind": "ClusterQueue",
		"metadata": {"name": "cq-inference", "labels": {"vulcan.dev/team": "inference"}},
		"spec": {
			"cohort": "vulcan-gpu-cohort",
			"resourceGroups": [{
				"coveredResources": ["cpu", "memory", "nvidia.com/mig-1g.5gb"],
				"flavors": [{"name": "mig-small"}],
			}],
		},
	}
	count(kueue.deny) == 0 with input as doc
}

test_deny_cq_without_cohort if {
	doc := {
		"kind": "ClusterQueue",
		"metadata": {"name": "cq-x", "labels": {"vulcan.dev/team": "inference"}},
		"spec": {
			"resourceGroups": [{
				"coveredResources": ["nvidia.com/mig-1g.5gb"],
				"flavors": [{"name": "mig-small"}],
			}],
		},
	}
	some msg in kueue.deny with input as doc
	contains(msg, "cohort")
}
