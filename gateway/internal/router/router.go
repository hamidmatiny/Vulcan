// Package router implements ADR-006 selection: latency + cost + health fallback.
package router

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/hamidmatiny/Vulcan/gateway/internal/breaker"
	"github.com/hamidmatiny/Vulcan/gateway/internal/catalog"
)

const PolicyID = "adr-006-v1"

// Constraints from the infer request (optional).
type Constraints struct {
	MaxLatencyMs           *float64 `json:"max_latency_ms"`
	MaxCostUSDPer1kTokens  *float64 `json:"max_cost_usd_per_1k_tokens"`
	PreferredRegion        string   `json:"preferred_region"`
	DataResidency          string   `json:"data_residency"`
	PreferredBackend       string   `json:"preferred_backend"`
}

type Attempt struct {
	Backend string `json:"backend"`
	Outcome string `json:"outcome"`
	Detail  string `json:"detail,omitempty"`
}

type Candidate struct {
	Backend           string   `json:"backend"`
	Rank              int      `json:"rank"`
	Score             float64  `json:"score"`
	LatencyP95Ms      *float64 `json:"latency_p95_ms"`
	CostUSDPer1k      *float64 `json:"cost_usd_per_1k_tokens"`
	DataSource        string   `json:"data_source"`
}

type Decision struct {
	SelectedBackend     string         `json:"selected_backend"`
	Policy              string         `json:"policy"`
	Candidates          []Candidate    `json:"candidates,omitempty"`
	Attempts            []Attempt      `json:"attempts"`
	ConstraintsApplied  map[string]any `json:"constraints_applied,omitempty"`
	Fallback            bool           `json:"fallback"`
}

type Router struct {
	Backends []catalog.Backend
	Breaker  *breaker.Breaker
	Client   *http.Client
	// Weights for ranking when both dimensions exist (ADR-006).
	WLatency float64
	WCost    float64
}

func New(backends []catalog.Backend, br *breaker.Breaker) *Router {
	return &Router{
		Backends: backends,
		Breaker:  br,
		Client:   &http.Client{Timeout: 3 * time.Second},
		WLatency: 0.7,
		WCost:    0.3,
	}
}

// Rank returns ordered candidates for modality under constraints (no health probe).
func (r *Router) Rank(modality string, c Constraints) ([]Candidate, []Attempt, map[string]any) {
	applied := map[string]any{}
	if c.MaxLatencyMs != nil {
		applied["max_latency_ms"] = *c.MaxLatencyMs
	}
	if c.MaxCostUSDPer1kTokens != nil {
		applied["max_cost_usd_per_1k_tokens"] = *c.MaxCostUSDPer1kTokens
	}
	if c.PreferredRegion != "" {
		applied["preferred_region"] = c.PreferredRegion
	}
	if c.DataResidency != "" {
		applied["data_residency"] = c.DataResidency
	}
	if c.PreferredBackend != "" {
		applied["preferred_backend"] = c.PreferredBackend
	}

	var skips []Attempt
	type scored struct {
		b     catalog.Backend
		score float64
	}
	var pool []scored

	for _, b := range r.Backends {
		if b.BaseURL == "" {
			skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: "base URL unset"})
			continue
		}
		if !b.Supports(modality) {
			skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: "unsupported modality " + modality})
			continue
		}
		forced := c.PreferredBackend != "" && c.PreferredBackend == b.Name
		if !b.AutoSelect && !forced {
			detail := b.ExcludeReason
			if detail == "" {
				detail = "not eligible for auto-select"
			}
			skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: detail})
			continue
		}
		if b.LatencyP95Ms == nil && !forced {
			skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: "no recorded latency data"})
			continue
		}
		if c.MaxLatencyMs != nil && b.LatencyP95Ms != nil && *b.LatencyP95Ms > *c.MaxLatencyMs {
			skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: fmt.Sprintf("p95 %.1f > max_latency_ms %.1f", *b.LatencyP95Ms, *c.MaxLatencyMs)})
			continue
		}
		if c.MaxCostUSDPer1kTokens != nil {
			if b.CostUSDPer1k == nil {
				skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: "no_cost_data (self-hosted benchmarks record latency only)"})
				continue
			}
			if *b.CostUSDPer1k > *c.MaxCostUSDPer1kTokens {
				skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: fmt.Sprintf("cost %.6f > max_cost %.6f", *b.CostUSDPer1k, *c.MaxCostUSDPer1kTokens)})
				continue
			}
		}
		regionWant := c.DataResidency
		if regionWant == "" {
			regionWant = c.PreferredRegion
		}
		if regionWant != "" && !strings.EqualFold(b.DataResidency, regionWant) && !strings.EqualFold(b.Region, regionWant) {
			skips = append(skips, Attempt{Backend: b.Name, Outcome: "skipped", Detail: "region/data_residency mismatch (have " + b.DataResidency + ")"})
			continue
		}
		pool = append(pool, scored{b: b, score: 0})
	}

	// Normalize latency/cost among remaining for scoring.
	var maxLat, maxCost float64
	for _, p := range pool {
		if p.b.LatencyP95Ms != nil {
			maxLat = math.Max(maxLat, *p.b.LatencyP95Ms)
		}
		if p.b.CostUSDPer1k != nil {
			maxCost = math.Max(maxCost, *p.b.CostUSDPer1k)
		}
	}
	for i := range pool {
		var latN, costN float64
		wLat, wCost := r.WLatency, r.WCost
		if pool[i].b.LatencyP95Ms != nil && maxLat > 0 {
			latN = *pool[i].b.LatencyP95Ms / maxLat
		} else {
			wLat = 0
		}
		if pool[i].b.CostUSDPer1k != nil && maxCost > 0 {
			costN = *pool[i].b.CostUSDPer1k / maxCost
		} else {
			wCost = 0
		}
		if wLat+wCost == 0 {
			pool[i].score = 0
		} else {
			pool[i].score = (wLat*latN + wCost*costN) / (wLat + wCost)
		}
		if c.PreferredBackend != "" && pool[i].b.Name == c.PreferredBackend {
			pool[i].score -= 0.05 // soft preference
		}
	}
	sort.SliceStable(pool, func(i, j int) bool {
		return pool[i].score < pool[j].score
	})

	cands := make([]Candidate, 0, len(pool))
	for i, p := range pool {
		src := p.b.LatencyDataSource
		if src == "" {
			src = p.b.CostDataSource
		}
		cands = append(cands, Candidate{
			Backend:      p.b.Name,
			Rank:         i + 1,
			Score:        p.score,
			LatencyP95Ms: p.b.LatencyP95Ms,
			CostUSDPer1k: p.b.CostUSDPer1k,
			DataSource:   src,
		})
	}
	return cands, skips, applied
}

func (r *Router) backendByName(name string) (catalog.Backend, bool) {
	for _, b := range r.Backends {
		if b.Name == name {
			return b, true
		}
	}
	return catalog.Backend{}, false
}

func (r *Router) healthy(ctx context.Context, baseURL string) (bool, string) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL+"/health", nil)
	if err != nil {
		return false, err.Error()
	}
	resp, err := r.Client.Do(req)
	if err != nil {
		return false, err.Error()
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode != http.StatusOK {
		return false, fmt.Sprintf("HTTP %d", resp.StatusCode)
	}
	var payload struct {
		Status string `json:"status"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return false, "invalid health json"
	}
	if payload.Status != "ok" {
		return false, "status=" + payload.Status
	}
	return true, "healthy"
}

// Select probes candidates in rank order with circuit breaking.
func (r *Router) Select(ctx context.Context, modality string, c Constraints) (catalog.Backend, Decision, error) {
	cands, skips, applied := r.Rank(modality, c)
	attempts := append([]Attempt{}, skips...)
	decision := Decision{
		Policy:             PolicyID,
		Candidates:         cands,
		ConstraintsApplied: applied,
		Attempts:           attempts,
	}
	if len(cands) == 0 {
		return catalog.Backend{}, decision, fmt.Errorf("no eligible backends for modality=%s", modality)
	}
	firstTry := true
	for _, cand := range cands {
		b, ok := r.backendByName(cand.Backend)
		if !ok || b.BaseURL == "" {
			continue
		}
		if allow, why := r.Breaker.Allow(b.Name); !allow {
			decision.Attempts = append(decision.Attempts, Attempt{Backend: b.Name, Outcome: "skipped", Detail: why})
			continue
		}
		okH, detail := r.healthy(ctx, b.BaseURL)
		if !okH {
			r.Breaker.Failure(b.Name)
			decision.Attempts = append(decision.Attempts, Attempt{Backend: b.Name, Outcome: "unhealthy", Detail: detail})
			firstTry = false
			continue
		}
		r.Breaker.Success(b.Name)
		decision.SelectedBackend = b.Name
		decision.Fallback = !firstTry
		outcome := "selected"
		if c.PreferredBackend == b.Name {
			outcome = "preferred"
		}
		decision.Attempts = append(decision.Attempts, Attempt{Backend: b.Name, Outcome: outcome, Detail: detail})
		return b, decision, nil
	}
	return catalog.Backend{}, decision, fmt.Errorf("all candidate backends unhealthy")
}
