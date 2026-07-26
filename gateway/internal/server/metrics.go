package server

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	inferRequests = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "vulcan_infer_requests_total",
		Help: "Total /v1/infer requests handled by the gateway",
	}, []string{"backend", "status", "modality"})

	inferLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "vulcan_infer_latency_seconds",
		Help:    "Gateway end-to-end infer latency",
		Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120},
	}, []string{"backend", "modality"})
)

func init() {
	// Ensure series exist for scrape/conformance (non-empty HELP/TYPE + samples).
	inferRequests.WithLabelValues(backendName, "ok", "llm")
	inferRequests.WithLabelValues(backendName, "error", "unknown")
	inferLatency.WithLabelValues(backendName, "llm")
}
