package breaker_test

import (
	"testing"
	"time"

	"github.com/hamidmatiny/Vulcan/gateway/internal/breaker"
)

func TestBreakerOpensAfterThreshold(t *testing.T) {
	b := breaker.New(2, 50*time.Millisecond)
	if ok, _ := b.Allow("x"); !ok {
		t.Fatal("expected allow")
	}
	b.Failure("x")
	if ok, _ := b.Allow("x"); !ok {
		t.Fatal("still allow after 1 failure")
	}
	b.Failure("x")
	if ok, why := b.Allow("x"); ok || why == "" {
		t.Fatalf("expected open, ok=%v why=%q", ok, why)
	}
	b.Success("x")
	if ok, _ := b.Allow("x"); !ok {
		t.Fatal("expected allow after success")
	}
}

func TestBreakerDefaults(t *testing.T) {
	b := breaker.New(0, 0)
	b.Failure("a")
	b.Failure("a")
	if ok, _ := b.Allow("a"); ok {
		t.Fatal("expected open with default threshold 2")
	}
}
