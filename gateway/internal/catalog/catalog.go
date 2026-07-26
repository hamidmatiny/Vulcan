// Package catalog loads recorded benchmark + pricing data for routing (ADR-006).
package catalog

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Backend is a selectable (or explicitly non-selectable) inference target.
type Backend struct {
	Name              string
	BaseURL           string
	Modalities        []string
	Region            string
	DataResidency     string
	LatencyP95Ms      *float64 // nil = no recorded latency
	CostUSDPer1k      *float64 // nil = no recorded $/1k (typical for self-hosted)
	LatencyDataSource string
	CostDataSource    string
	AutoSelect        bool   // false → excluded unless preferred_backend forces it
	ExcludeReason     string // human-readable when AutoSelect=false
}

type benchmarkFile struct {
	Backend  string `json:"backend"`
	Modality string `json:"modality"`
	Metrics  struct {
		LatencyMs struct {
			P95 float64 `json:"p95"`
		} `json:"latency_ms"`
	} `json:"metrics"`
}

type bedrockPricingFile struct {
	Source     string `json:"source"`
	RegionHint string `json:"region_hint"`
	Models     map[string]struct {
		InputUSDPer1k  float64 `json:"input_usd_per_1k_tokens"`
		OutputUSDPer1k float64 `json:"output_usd_per_1k_tokens"`
		TypicalLatency struct {
			P95 float64 `json:"p95"`
		} `json:"typical_latency_ms"`
	} `json:"models"`
}

// Load builds the catalog from env URLs + on-disk recorded data.
func Load(benchmarkDir, bedrockPricingPath string) ([]Backend, error) {
	llmLatency, err := loadLLMBenchmarks(benchmarkDir)
	if err != nil {
		return nil, err
	}

	var bedrock *Backend
	if bedrockPricingPath != "" {
		b, err := loadBedrock(bedrockPricingPath, envURL("VULCAN_BEDROCK_URL"))
		if err != nil {
			return nil, err
		}
		bedrock = b
	}

	out := []Backend{
		backendFromBench("bentoml", envURL("VULCAN_BENTOML_URL"), []string{"llm", "vision"}, llmLatency),
		backendFromBench("ray-serve", envURL("VULCAN_RAY_SERVE_URL"), []string{"llm", "vision"}, llmLatency),
		backendFromBench("triton", envURL("VULCAN_TRITON_URL"), []string{"llm", "vision"}, llmLatency),
		backendFromBench("vllm", envURL("VULCAN_VLLM_URL"), []string{"llm"}, llmLatency),
		{
			Name:          "kserve",
			BaseURL:       envURL("VULCAN_KSERVE_URL"),
			Modalities:    []string{"llm", "vision"},
			Region:        envOr("VULCAN_KSERVE_REGION", "local"),
			DataResidency: envOr("VULCAN_KSERVE_REGION", "local"),
			AutoSelect:    false,
			ExcludeReason: "no benchmark/results entry for kserve (KServe wraps other backends; measure the shim URL before enabling auto-select)",
		},
		{
			Name:          "sagemaker",
			BaseURL:       envURL("VULCAN_SAGEMAKER_URL"),
			Modalities:    []string{"llm"},
			Region:        envOr("VULCAN_SAGEMAKER_REGION", "us-east-1"),
			DataResidency: envOr("VULCAN_SAGEMAKER_REGION", "us-east-1"),
			AutoSelect:    false,
			ExcludeReason: "no benchmark/results entry comparable to self-hosted k6 runs; excluded from automated selection (see gateway/README.md)",
		},
	}
	if bedrock != nil {
		out = append(out, *bedrock)
	} else {
		out = append(out, Backend{
			Name:          "bedrock",
			BaseURL:       envURL("VULCAN_BEDROCK_URL"),
			Modalities:    []string{"llm"},
			AutoSelect:    false,
			ExcludeReason: "bedrock pricing-reference.json not loaded",
		})
	}
	return out, nil
}

func envURL(key string) string {
	return strings.TrimRight(strings.TrimSpace(os.Getenv(key)), "/")
}

func envOr(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

func loadLLMBenchmarks(dir string) (map[string]float64, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("benchmark dir %s: %w", dir, err)
	}
	type hit struct {
		p95  float64
		cpu  bool
		name string
	}
	best := map[string]hit{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") || e.Name() == "schema.json" {
			continue
		}
		path := filepath.Join(dir, e.Name())
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		var bf benchmarkFile
		if err := json.Unmarshal(raw, &bf); err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		if bf.Modality != "llm" || bf.Backend == "" || bf.Backend == "gateway" {
			continue
		}
		cpu := strings.HasSuffix(e.Name(), "-cpu.json")
		prev, ok := best[bf.Backend]
		if ok && prev.cpu && !cpu {
			continue // keep CI *-cpu.json over other artifacts
		}
		if ok && prev.cpu == cpu && prev.name < e.Name() {
			continue // stable pick among equals
		}
		best[bf.Backend] = hit{p95: bf.Metrics.LatencyMs.P95, cpu: cpu, name: e.Name()}
	}
	out := map[string]float64{}
	for name, h := range best {
		out[name] = h.p95
	}
	return out, nil
}

func backendFromBench(name, url string, mods []string, lat map[string]float64) Backend {
	b := Backend{
		Name:          name,
		BaseURL:       url,
		Modalities:    mods,
		Region:        "local",
		DataResidency: "local",
		AutoSelect:    true,
	}
	if p95, ok := lat[name]; ok {
		v := p95
		b.LatencyP95Ms = &v
		b.LatencyDataSource = fmt.Sprintf("benchmark/results/%s-cpu.json", name)
		if name == "ray-serve" {
			b.LatencyDataSource = "benchmark/results/ray-serve-cpu.json"
		}
	} else {
		b.AutoSelect = false
		b.ExcludeReason = "no llm benchmark/results entry"
	}
	// Self-hosted: no recorded $/1k in-repo — leave CostUSDPer1k nil (ADR-006).
	return b
}

func loadBedrock(path, url string) (*Backend, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("bedrock pricing: %w", err)
	}
	var pf bedrockPricingFile
	if err := json.Unmarshal(raw, &pf); err != nil {
		return nil, err
	}
	if pf.Source != "static_reference" {
		return nil, fmt.Errorf("bedrock pricing source must be static_reference")
	}
	// Use Titan express as the default Bedrock candidate (documented in pricing file).
	model, ok := pf.Models["amazon.titan-text-express-v1"]
	if !ok {
		return nil, fmt.Errorf("amazon.titan-text-express-v1 missing from pricing-reference.json")
	}
	// Cost for routing: input+output blended for 1k in + 1k out → average per 1k tokens.
	blend := (model.InputUSDPer1k + model.OutputUSDPer1k) / 2
	p95 := model.TypicalLatency.P95
	region := "us-east-1"
	if pf.RegionHint != "" {
		// "us-east-1 list-price ballpark..."
		parts := strings.Fields(pf.RegionHint)
		if len(parts) > 0 {
			region = parts[0]
		}
	}
	b := &Backend{
		Name:              "bedrock",
		BaseURL:           url,
		Modalities:        []string{"llm"},
		Region:            region,
		DataResidency:     region,
		LatencyP95Ms:      &p95,
		CostUSDPer1k:      &blend,
		LatencyDataSource: "bedrock-gateway/pricing-reference.json",
		CostDataSource:    "bedrock-gateway/pricing-reference.json",
		AutoSelect:        url != "",
	}
	if url == "" {
		b.AutoSelect = false
		b.ExcludeReason = "VULCAN_BEDROCK_URL unset (pricing loaded; enable URL to auto-select)"
	}
	return b, nil
}

// Supports reports whether backend handles modality.
func (b Backend) Supports(modality string) bool {
	for _, m := range b.Modalities {
		if m == modality {
			return true
		}
	}
	return false
}
