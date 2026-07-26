package server_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/hamidmatiny/Vulcan/gateway/internal/breaker"
	"github.com/hamidmatiny/Vulcan/gateway/internal/catalog"
	"github.com/hamidmatiny/Vulcan/gateway/internal/router"
	"github.com/hamidmatiny/Vulcan/gateway/internal/server"
)

func TestInferFallsBackAndSurfacesReason(t *testing.T) {
	// Primary (preferred by latency) becomes unhealthy mid-run.
	primaryUp := true
	primary := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			if !primaryUp {
				_ = json.NewEncoder(w).Encode(map[string]any{
					"status": "error", "backend": "primary", "model_id": "reference-tiny-llm", "version": "1", "mode": "cpu",
				})
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"status": "ok", "backend": "primary", "model_id": "reference-tiny-llm", "version": "1", "mode": "cpu",
			})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"request_id": "t1", "modality": "llm", "model_id": "reference-tiny-llm",
			"output": map[string]any{"text": "from-primary", "finish_reason": "stop"},
			"latency_ms": 1.0,
		})
	}))
	defer primary.Close()

	secondary := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"status": "ok", "backend": "secondary", "model_id": "reference-tiny-llm", "version": "1", "mode": "cpu",
			})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"request_id": "t1", "modality": "llm", "model_id": "reference-tiny-llm",
			"output": map[string]any{"text": "from-secondary", "finish_reason": "stop"},
			"latency_ms": 2.0,
		})
	}))
	defer secondary.Close()

	p95a, p95b := 10.0, 20.0
	backends := []catalog.Backend{
		{Name: "primary", BaseURL: primary.URL, Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: &p95a, Region: "local", DataResidency: "local", LatencyDataSource: "test"},
		{Name: "secondary", BaseURL: secondary.URL, Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: &p95b, Region: "local", DataResidency: "local", LatencyDataSource: "test"},
	}
	r := router.New(backends, breaker.New(2, 0))
	r.Client = primary.Client()

	dir := t.TempDir()
	resPath := filepath.Join(dir, "resource-requirements.json")
	if err := os.WriteFile(resPath, []byte(`{"model_id":"reference-tiny-llm","backend":"gateway","gpu_memory_mib":{"min":0,"max":0},"supports_mig":false,"supports_quantization":false,"cold_start_seconds":{"min":0,"max":1},"cpu_dev_mode":true}`), 0o644); err != nil {
		t.Fatal(err)
	}
	srv, err := server.New(r, resPath)
	if err != nil {
		t.Fatal(err)
	}
	gw := httptest.NewServer(srv.Handler())
	defer gw.Close()

	payload := []byte(`{"request_id":"t1","modality":"llm","model_id":"reference-tiny-llm","input":{"messages":[{"role":"user","content":"hi"}]}}`)

	// First request → primary.
	resp, err := http.Post(gw.URL+"/v1/infer", "application/json", bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	var body map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&body)
	resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatalf("status %d body %#v", resp.StatusCode, body)
	}
	routing := body["routing"].(map[string]any)
	if routing["selected_backend"] != "primary" {
		t.Fatalf("want primary got %#v", routing)
	}

	// Kill primary; next request must fall back with reason.
	primaryUp = false
	resp2, err := http.Post(gw.URL+"/v1/infer", "application/json", bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	var body2 map[string]any
	_ = json.NewDecoder(resp2.Body).Decode(&body2)
	resp2.Body.Close()
	if resp2.StatusCode != 200 {
		t.Fatalf("status %d body %#v", resp2.StatusCode, body2)
	}
	routing2 := body2["routing"].(map[string]any)
	if routing2["selected_backend"] != "secondary" {
		t.Fatalf("want secondary got %#v", routing2)
	}
	if routing2["fallback"] != true {
		t.Fatalf("expected fallback true: %#v", routing2)
	}
	out := body2["output"].(map[string]any)
	if out["text"] != "from-secondary" {
		t.Fatalf("unexpected output %#v", out)
	}
	attempts, _ := routing2["attempts"].([]any)
	found := false
	for _, a := range attempts {
		m := a.(map[string]any)
		if m["backend"] == "primary" && m["outcome"] == "unhealthy" {
			found = true
		}
	}
	if !found {
		t.Fatalf("missing unhealthy attempt: %#v", attempts)
	}
}
