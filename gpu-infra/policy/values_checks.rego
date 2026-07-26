# Validate GPU Operator Helm values YAML (parsed as unstructured input).
package vulcan.gpu_operator_values

import future.keywords.contains
import future.keywords.if

deny contains msg if {
	input.driver
	input.driver.enabled != false
	msg := "values-eks.yaml: driver.enabled must be false for EKS GPU AMI (preinstalled drivers)"
}

deny contains msg if {
	input.devicePlugin
	input.devicePlugin.enabled != true
	msg := "device plugin must remain enabled (separate from driver/toolkit)"
}

deny contains msg if {
	input.toolkit
	not input.toolkit.enabled
	msg := "toolkit.enabled should be true unless using a custom preinstalled toolkit path"
}

deny contains msg if {
	input.migManager
	input.migManager.enabled != true
	msg := "migManager.enabled must be true for ADR-003 profiles"
}

deny contains msg if {
	input.daemonsets
	not input.daemonsets.tolerations
	msg := "daemonsets.tolerations required for nvidia.com/gpu NoSchedule taint"
}
