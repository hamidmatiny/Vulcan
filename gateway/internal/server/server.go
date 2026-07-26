package server

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
	"time"

	"github.com/hamidmatiny/Vulcan/gateway/internal/breaker"
	"github.com/hamidmatiny/Vulcan/gateway/internal/catalog"
	"github.com/hamidmatiny/Vulcan/gateway/internal/router"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

const (
	backendName    = "gateway"
	backendVersion = "0.13.0"
)

type Server struct {
	Router      *router.Router
	Resources   map[string]any
	ProxyClient *http.Client
	ready       atomic.Bool
}

func New(r *router.Router, resourcesPath string) (*Server, error) {
	raw, err := os.ReadFile(resourcesPath)
	if err != nil {
		return nil, err
	}
	var res map[string]any
	if err := json.Unmarshal(raw, &res); err != nil {
		return nil, err
	}
	s := &Server{
		Router:      r,
		Resources:   res,
		ProxyClient: &http.Client{Timeout: 120 * time.Second},
	}
	s.ready.Store(true)
	return s, nil
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /metrics", promhttp.Handler().ServeHTTP)
	mux.HandleFunc("GET /v1/resources", s.handleResources)
	mux.HandleFunc("POST /v1/infer", s.handleInfer)
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	status := "ok"
	code := http.StatusOK
	if !s.ready.Load() {
		status = "starting"
		code = http.StatusServiceUnavailable
	}
	writeJSON(w, code, map[string]any{
		"status":   status,
		"backend":  backendName,
		"model_id": "reference-tiny-llm",
		"version":  backendVersion,
		"mode":     "cpu",
		"detail":   "routing gateway; selects among catalogued backends (ADR-006)",
	})
}

func (s *Server) handleResources(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, s.Resources)
}

type inferRequest struct {
	RequestID   string              `json:"request_id"`
	Modality    string              `json:"modality"`
	ModelID     string              `json:"model_id"`
	Input       json.RawMessage     `json:"input"`
	Constraints *router.Constraints `json:"constraints"`
	Metadata    map[string]string   `json:"metadata"`
}

func (s *Server) handleInfer(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	body, err := io.ReadAll(io.LimitReader(r.Body, 32<<20))
	if err != nil {
		inferRequests.WithLabelValues(backendName, "error", "unknown").Inc()
		writeErr(w, http.StatusBadRequest, "invalid_json", "unable to read body", nil)
		return
	}
	var req inferRequest
	if err := json.Unmarshal(body, &req); err != nil {
		inferRequests.WithLabelValues(backendName, "error", "unknown").Inc()
		writeErr(w, http.StatusBadRequest, "invalid_json", "body must be JSON", nil)
		return
	}
	if req.RequestID == "" || req.Modality == "" || req.ModelID == "" {
		inferRequests.WithLabelValues(backendName, "error", "unknown").Inc()
		writeErr(w, http.StatusBadRequest, "invalid_request", "request_id, modality, and model_id are required", strPtr(req.RequestID))
		return
	}
	if req.Modality != "llm" && req.Modality != "vision" {
		inferRequests.WithLabelValues(backendName, "error", "unknown").Inc()
		writeErr(w, http.StatusBadRequest, "invalid_request", "unsupported modality: "+req.Modality, &req.RequestID)
		return
	}
	c := router.Constraints{}
	if req.Constraints != nil {
		c = *req.Constraints
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	selected, decision, err := s.Router.Select(ctx, req.Modality, c)
	if err != nil {
		inferRequests.WithLabelValues(backendName, "error", req.Modality).Inc()
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"error":      "no_backend",
			"message":    err.Error(),
			"request_id": req.RequestID,
			"routing":    decision,
		})
		return
	}

	// Strip gateway-only fields before forwarding (downstream backends reject unknown keys).
	fwdBody, err := stripGatewayFields(body)
	if err != nil {
		inferRequests.WithLabelValues(backendName, "error", req.Modality).Inc()
		writeErr(w, http.StatusBadRequest, "invalid_request", err.Error(), &req.RequestID)
		return
	}
	proxyReq, err := http.NewRequestWithContext(r.Context(), http.MethodPost, selected.BaseURL+"/v1/infer", bytes.NewReader(fwdBody))
	if err != nil {
		inferRequests.WithLabelValues(backendName, "error", req.Modality).Inc()
		writeErr(w, http.StatusInternalServerError, "proxy_error", err.Error(), &req.RequestID)
		return
	}
	proxyReq.Header.Set("Content-Type", "application/json")
	resp, err := s.ProxyClient.Do(proxyReq)
	if err != nil {
		s.Router.Breaker.Failure(selected.Name)
		inferRequests.WithLabelValues(backendName, "error", req.Modality).Inc()
		decision.Attempts = append(decision.Attempts, router.Attempt{Backend: selected.Name, Outcome: "error", Detail: err.Error()})
		writeJSON(w, http.StatusBadGateway, map[string]any{
			"error":      "infer_failed",
			"message":    err.Error(),
			"request_id": req.RequestID,
			"routing":    decision,
		})
		return
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if resp.StatusCode != http.StatusOK {
		s.Router.Breaker.Failure(selected.Name)
		inferRequests.WithLabelValues(backendName, "error", req.Modality).Inc()
		var passthrough map[string]any
		if json.Unmarshal(respBody, &passthrough) == nil {
			passthrough["routing"] = decision
			writeJSON(w, resp.StatusCode, passthrough)
			return
		}
		writeJSON(w, resp.StatusCode, map[string]any{
			"error":      "infer_failed",
			"message":    string(respBody),
			"request_id": req.RequestID,
			"routing":    decision,
		})
		return
	}

	var out map[string]any
	if err := json.Unmarshal(respBody, &out); err != nil {
		inferRequests.WithLabelValues(backendName, "error", req.Modality).Inc()
		writeErr(w, http.StatusBadGateway, "infer_failed", "backend returned non-JSON", &req.RequestID)
		return
	}
	out["routing"] = decision
	out["latency_ms"] = float64(time.Since(started).Milliseconds())
	inferRequests.WithLabelValues(backendName, "ok", req.Modality).Inc()
	inferLatency.WithLabelValues(backendName, req.Modality).Observe(time.Since(started).Seconds())
	writeJSON(w, http.StatusOK, out)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, code int, errCode, msg string, requestID *string) {
	body := map[string]any{"error": errCode, "message": msg}
	if requestID != nil && *requestID != "" {
		body["request_id"] = *requestID
	}
	writeJSON(w, code, body)
}

func strPtr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func stripGatewayFields(body []byte) ([]byte, error) {
	var m map[string]any
	if err := json.Unmarshal(body, &m); err != nil {
		return nil, err
	}
	delete(m, "constraints")
	return json.Marshal(m)
}

// NewFromEnv builds a fully wired server for main/tests.
func NewFromEnv(benchmarkDir, bedrockPricing, resourcesPath string) (*Server, error) {
	backends, err := catalog.Load(benchmarkDir, bedrockPricing)
	if err != nil {
		return nil, err
	}
	br := breaker.New(2, 10*time.Second)
	r := router.New(backends, br)
	if v := os.Getenv("VULCAN_GATEWAY_HEALTH_TIMEOUT_MS"); v != "" {
		if ms, err := strconv.Atoi(v); err == nil && ms > 0 {
			r.Client.Timeout = time.Duration(ms) * time.Millisecond
		}
	}
	return New(r, resourcesPath)
}
