package otel_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hamidmatiny/Vulcan/gateway/internal/otel"
)

func TestSetupNoopWithoutEndpoint(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	shutdown, err := otel.Setup(context.Background(), "gateway")
	if err != nil {
		t.Fatal(err)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatal(err)
	}
	h := otel.WrapHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(204)
	}), "test")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if rec.Code != 204 {
		t.Fatalf("code %d", rec.Code)
	}
	req, _ := http.NewRequest(http.MethodGet, "http://example", nil)
	otel.InjectTraceHeaders(context.Background(), req)
	if otel.Transport(nil) == nil {
		t.Fatal("expected transport")
	}
}
