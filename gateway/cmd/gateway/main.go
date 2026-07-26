package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/hamidmatiny/Vulcan/gateway/internal/server"
)

func main() {
	port := envOr("PORT", "9007")
	bench := envOr("VULCAN_BENCHMARK_DIR", filepath.Join("..", "..", "benchmark", "results"))
	pricing := envOr("VULCAN_BEDROCK_PRICING", filepath.Join("..", "..", "bedrock-gateway", "pricing-reference.json"))
	resources := envOr("VULCAN_RESOURCES_PATH", "resource-requirements.json")

	srv, err := server.NewFromEnv(bench, pricing, resources)
	if err != nil {
		log.Fatalf("gateway init: %v", err)
	}
	addr := ":" + port
	log.Printf("vulcan gateway listening on %s (ADR-006)", addr)
	if err := http.ListenAndServe(addr, srv.Handler()); err != nil {
		log.Fatal(err)
	}
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
