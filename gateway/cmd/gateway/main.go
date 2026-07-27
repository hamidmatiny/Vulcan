package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/hamidmatiny/Vulcan/gateway/internal/otel"
	"github.com/hamidmatiny/Vulcan/gateway/internal/server"
)

func main() {
	port := envOr("PORT", "9007")
	bench := envOr("VULCAN_BENCHMARK_DIR", filepath.Join("..", "..", "benchmark", "results"))
	pricing := envOr("VULCAN_BEDROCK_PRICING", filepath.Join("..", "..", "bedrock-gateway", "pricing-reference.json"))
	resources := envOr("VULCAN_RESOURCES_PATH", "resource-requirements.json")

	ctx := context.Background()
	shutdown, err := otel.Setup(ctx, "gateway")
	if err != nil {
		log.Fatalf("otel: %v", err)
	}
	defer func() {
		c, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = shutdown(c)
	}()

	srv, err := server.NewFromEnv(bench, pricing, resources)
	if err != nil {
		log.Fatalf("gateway init: %v", err)
	}
	handler := otel.WrapHandler(srv.Handler(), "vulcan-gateway")

	httpSrv := &http.Server{Addr: ":" + port, Handler: handler}
	go func() {
		log.Printf("vulcan gateway listening on %s (ADR-006; otel=%v)", httpSrv.Addr, os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT") != "")
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	c, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(c)
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
