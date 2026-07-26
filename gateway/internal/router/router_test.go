package router_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hamidmatiny/Vulcan/gateway/internal/breaker"
	"github.com/hamidmatiny/Vulcan/gateway/internal/catalog"
	"github.com/hamidmatiny/Vulcan/gateway/internal/router"
)

func p95(v float64) *float64 { return &v }
func cost(v float64) *float64 { return &v }

func TestRankPrefersLowerLatencyFromRecordedData(t *testing.T) {
	backends := []catalog.Backend{
		{Name: "slow", BaseURL: "http://slow", Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: p95(2000), Region: "local", DataResidency: "local", LatencyDataSource: "bench/slow.json"},
		{Name: "fast", BaseURL: "http://fast", Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: p95(200), Region: "local", DataResidency: "local", LatencyDataSource: "bench/fast.json"},
	}
	r := router.New(backends, breaker.New(2, 0))
	cands, _, _ := r.Rank("llm", router.Constraints{})
	if len(cands) != 2 || cands[0].Backend != "fast" {
		t.Fatalf("expected fast first, got %#v", cands)
	}
}

func TestCostConstraintSkipsNoCostData(t *testing.T) {
	maxCost := 0.001
	backends := []catalog.Backend{
		{Name: "bentoml", BaseURL: "http://b", Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: p95(100), Region: "local", DataResidency: "local"},
		{Name: "bedrock", BaseURL: "http://br", Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: p95(400), CostUSDPer1k: cost(0.0004), Region: "us-east-1", DataResidency: "us-east-1"},
	}
	r := router.New(backends, breaker.New(2, 0))
	cands, skips, _ := r.Rank("llm", router.Constraints{MaxCostUSDPer1kTokens: &maxCost})
	if len(cands) != 1 || cands[0].Backend != "bedrock" {
		t.Fatalf("expected only bedrock, cands=%#v skips=%#v", cands, skips)
	}
}

func TestSageMakerExcludedWithoutForce(t *testing.T) {
	backends := []catalog.Backend{
		{Name: "sagemaker", BaseURL: "http://sm", Modalities: []string{"llm"}, AutoSelect: false, ExcludeReason: "no benchmark", LatencyP95Ms: p95(100)},
		{Name: "bentoml", BaseURL: "http://b", Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: p95(100), Region: "local", DataResidency: "local"},
	}
	r := router.New(backends, breaker.New(2, 0))
	cands, skips, _ := r.Rank("llm", router.Constraints{})
	if len(cands) != 1 || cands[0].Backend != "bentoml" {
		t.Fatalf("unexpected %#v %#v", cands, skips)
	}
}

func TestSelectFallsBackWhenPreferredUnhealthy(t *testing.T) {
	bad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "error", "backend": "bad", "model_id": "x", "version": "1", "mode": "cpu"})
	}))
	defer bad.Close()
	good := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "ok", "backend": "good", "model_id": "x", "version": "1", "mode": "cpu"})
	}))
	defer good.Close()

	backends := []catalog.Backend{
		{Name: "bad", BaseURL: bad.URL, Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: p95(50), Region: "local", DataResidency: "local"},
		{Name: "good", BaseURL: good.URL, Modalities: []string{"llm"}, AutoSelect: true, LatencyP95Ms: p95(80), Region: "local", DataResidency: "local"},
	}
	r := router.New(backends, breaker.New(2, 0))
	r.Client = bad.Client()
	sel, dec, err := r.Select(context.Background(), "llm", router.Constraints{})
	if err != nil {
		t.Fatal(err)
	}
	if sel.Name != "good" {
		t.Fatalf("selected %s", sel.Name)
	}
	if !dec.Fallback {
		t.Fatalf("expected fallback=true decision=%#v", dec)
	}
	foundUnhealthy := false
	for _, a := range dec.Attempts {
		if a.Backend == "bad" && a.Outcome == "unhealthy" {
			foundUnhealthy = true
		}
	}
	if !foundUnhealthy {
		t.Fatalf("expected unhealthy attempt: %#v", dec.Attempts)
	}
}
