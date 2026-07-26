{{- define "vulcan-kserve.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "vulcan-kserve.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "vulcan-kserve.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "vulcan-kserve.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "vulcan-kserve.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- range $k, $v := .Values.commonLabels }}
{{ $k }}: {{ $v | quote }}
{{- end }}
{{- end }}

{{- define "vulcan-kserve.annotations" -}}
serving.kserve.io/deploymentMode: {{ .Values.deploymentMode | quote }}
{{- end }}
