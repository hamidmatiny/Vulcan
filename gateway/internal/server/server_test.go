package server_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/hamidmatiny/Vulcan/gateway/internal/breaker"
	"github.com/hamidmatiny/Vulcan/gateway/internal/catalog"
	"github.com/hamidmatiny/Vulcan/gateway/internal/router"
	"github.com/hamidmatiny/Vulcan/gateway/internal/server"
)

func resourcesFile(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "resource-requirements.json")
	body := `{"model_id":"reference-tiny-llm","backend":"gateway","gpu_memory_mib":{"min":0,"max":0},"supports_mig":false,"supports_quantization":false,"cold_start_seconds":{"min":0,"max":1},"cpu_dev_mode":true}`
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func backendServer(t *testing.T, name string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/health":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"status": "ok", "backend": name, "model_id": "reference-tiny-llm", "version": "1", "mode": "cpu",
			})
		case "/v1/infer":
			var body map[string]any
			_ = json.NewDecoder(r.Body).Decode(&body)
			if _, ok := body["constraints"]; ok {
				http.Error(w, "constraints leaked", 400)
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"request_id": body["request_id"], "modality": "llm", "model_id": "reference-tiny-llm",
				"output": map[string]any{"text": "ok", "finish_reason": "stop"}, "latency_ms": 1.0,
			})
		default:
			http.NotFound(w, r)
		}
	}))
}

func TestHealthMetricsResources(t *testing.T) {
	be := backendServer(t, "b")
	defer be.Close()
	p95 := 10.0
	r := router.New([]catalog.Backend{{
		Name: "b", BaseURL: be.URL, Modalities: []string{"llm"}, AutoSelect: true,
		LatencyP95Ms: &p95, Region: "local", DataResidency: "local",
	}}, breaker.New(2, 0))
	r.Client = be.Client()
	srv, err := server.New(r, resourcesFile(t))
	if err != nil {
		t.Fatal(err)
	}
	gw := httptest.NewServer(srv.Handler())
	defer gw.Close()

	for _, path := range []string{"/health", "/metrics", "/v1/resources"} {
		resp, err := http.Get(gw.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		if resp.StatusCode != 200 {
			t.Fatalf("%s → %d", path, resp.StatusCode)
		}
		_ = resp.Body.Close()
	}
	h, _ := http.Get(gw.URL + "/health")
	var health map[string]any
	_ = json.NewDecoder(h.Body).Decode(&health)
	_ = h.Body.Close()
	if health["backend"] != "gateway" || health["status"] != "ok" {
		t.Fatalf("%#v", health)
	}
}

func TestInferRejectsBadJSONAndStripsConstraints(t *testing.T) {
	be := backendServer(t, "b")
	defer be.Close()
	p95 := 10.0
	r := router.New([]catalog.Backend{{
		Name: "b", BaseURL: be.URL, Modalities: []string{"llm"}, AutoSelect: true,
		LatencyP95Ms: &p95, Region: "local", DataResidency: "local",
	}}, breaker.New(2, 0))
	r.Client = be.Client()
	srv, err := server.New(r, resourcesFile(t))
	if err != nil {
		t.Fatal(err)
	}
	gw := httptest.NewServer(srv.Handler())
	defer gw.Close()

	bad, err := http.Post(gw.URL+"/v1/infer", "application/json", strings.NewReader("{"))
	if err != nil {
		t.Fatal(err)
	}
	if bad.StatusCode != 400 {
		t.Fatalf("bad json → %d", bad.StatusCode)
	}
	_ = bad.Body.Close()

	payload := []byte(`{"request_id":"t1","modality":"llm","model_id":"reference-tiny-llm","input":{"messages":[{"role":"user","content":"hi"}]},"constraints":{"max_latency_ms":5000}}`)
	ok, err := http.Post(gw.URL+"/v1/infer", "application/json", bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	defer ok.Body.Close()
	if ok.StatusCode != 200 {
		t.Fatalf("infer → %d", ok.StatusCode)
	}
	var out map[string]any
	_ = json.NewDecoder(ok.Body).Decode(&out)
	if out["routing"] == nil {
		t.Fatal("expected routing")
	}
}

func TestNewFromEnv(t *testing.T) {
	dir := t.TempDir()
	bench := filepath.Join(dir, "bench")
	if err := os.MkdirAll(bench, 0o755); err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(map[string]any{
		"schema_version": 1, "backend": "bentoml", "modality": "llm", "model_id": "reference-tiny-llm",
		"target_url": "http://x", "started_at": "2026-01-01T00:00:00Z", "duration_seconds": 1, "vus": 1,
		"metrics": map[string]any{"requests_total": 1, "error_rate": 0, "throughput_rps": 1, "latency_ms": map[string]any{"p50": 1, "p95": 1, "p99": 1}},
	})
	_ = os.WriteFile(filepath.Join(bench, "bentoml-cpu.json"), raw, 0o644)
	pricing := filepath.Join(dir, "pricing.json")
	_ = os.WriteFile(pricing, []byte(`{"schema_version":1,"source":"static_reference","models":{"amazon.titan-text-express-v1":{"input_usd_per_1k_tokens":0.1,"output_usd_per_1k_tokens":0.2,"typical_latency_ms":{"p50":1,"p95":2}}}}`), 0o644)
	t.Setenv("VULCAN_BENTOML_URL", "http://127.0.0.1:9")
	srv, err := server.NewFromEnv(bench, pricing, resourcesFile(t))
	if err != nil {
		t.Fatal(err)
	}
	if srv == nil {
		t.Fatal("nil server")
	}
}
