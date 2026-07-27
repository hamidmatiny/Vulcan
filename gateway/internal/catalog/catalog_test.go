package catalog_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/hamidmatiny/Vulcan/gateway/internal/catalog"
)

func TestLoadPrefersCPUBenchmarksAndExcludesSageMaker(t *testing.T) {
	dir := t.TempDir()
	writeBench := func(name, backend string, p95 float64) {
		raw, _ := json.Marshal(map[string]any{
			"schema_version": 1,
			"backend":        backend,
			"modality":       "llm",
			"model_id":       "reference-tiny-llm",
			"target_url":     "http://x",
			"started_at":     "2026-01-01T00:00:00Z",
			"duration_seconds": 1,
			"vus":            1,
			"metrics": map[string]any{
				"requests_total": 1,
				"error_rate":     0,
				"throughput_rps": 1,
				"latency_ms":     map[string]any{"p50": p95, "p95": p95, "p99": p95},
			},
		})
		if err := os.WriteFile(filepath.Join(dir, name), raw, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	writeBench("bentoml-cpu.json", "bentoml", 100)
	writeBench("bentoml-other.json", "bentoml", 999)
	writeBench("ray-serve-cpu.json", "ray-serve", 80)
	writeBench("triton-cpu.json", "triton", 200)
	writeBench("vllm-cpu.json", "vllm", 150)

	pricing := filepath.Join(dir, "pricing.json")
	if err := os.WriteFile(pricing, []byte(`{
	  "schema_version": 1,
	  "source": "static_reference",
	  "region_hint": "us-east-1 list-price",
	  "models": {
	    "amazon.titan-text-express-v1": {
	      "input_usd_per_1k_tokens": 0.0002,
	      "output_usd_per_1k_tokens": 0.0006,
	      "typical_latency_ms": {"p50": 100, "p95": 400}
	    }
	  }
	}`), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("VULCAN_BENTOML_URL", "http://bentoml:9000")
	t.Setenv("VULCAN_RAY_SERVE_URL", "http://ray:9002")
	t.Setenv("VULCAN_TRITON_URL", "http://triton:9003")
	t.Setenv("VULCAN_VLLM_URL", "http://vllm:9004")
	t.Setenv("VULCAN_BEDROCK_URL", "")

	backends, err := catalog.Load(dir, pricing)
	if err != nil {
		t.Fatal(err)
	}
	byName := map[string]catalog.Backend{}
	for _, b := range backends {
		byName[b.Name] = b
	}
	if byName["bentoml"].LatencyP95Ms == nil || *byName["bentoml"].LatencyP95Ms != 100 {
		t.Fatalf("expected cpu p95=100, got %#v", byName["bentoml"].LatencyP95Ms)
	}
	if byName["sagemaker"].AutoSelect {
		t.Fatal("sagemaker must not auto-select")
	}
	if byName["kserve"].AutoSelect {
		t.Fatal("kserve must not auto-select")
	}
	if byName["bedrock"].AutoSelect {
		t.Fatal("bedrock without URL must not auto-select")
	}
	if !byName["bentoml"].Supports("llm") || byName["vllm"].Supports("vision") {
		t.Fatal("modality support mismatch")
	}
}

func TestLoadBedrockAutoSelectWhenURLSet(t *testing.T) {
	dir := t.TempDir()
	pricing := filepath.Join(dir, "pricing.json")
	if err := os.WriteFile(pricing, []byte(`{
	  "schema_version": 1,
	  "source": "static_reference",
	  "region_hint": "us-east-1",
	  "models": {
	    "amazon.titan-text-express-v1": {
	      "input_usd_per_1k_tokens": 0.0002,
	      "output_usd_per_1k_tokens": 0.0006,
	      "typical_latency_ms": {"p50": 100, "p95": 400}
	    }
	  }
	}`), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("VULCAN_BEDROCK_URL", "http://bedrock:9006")
	backends, err := catalog.Load(dir, pricing)
	if err != nil {
		t.Fatal(err)
	}
	for _, b := range backends {
		if b.Name == "bedrock" {
			if !b.AutoSelect || b.CostUSDPer1k == nil {
				t.Fatalf("bedrock %#v", b)
			}
			return
		}
	}
	t.Fatal("bedrock missing")
}
