package breaker

import (
	"sync"
	"time"
)

// Breaker tracks consecutive health failures per backend (simple circuit breaker).
type Breaker struct {
	mu          sync.Mutex
	failures    map[string]int
	openUntil   map[string]time.Time
	threshold   int
	cooldown    time.Duration
	now         func() time.Time
}

func New(threshold int, cooldown time.Duration) *Breaker {
	if threshold < 1 {
		threshold = 2
	}
	if cooldown <= 0 {
		cooldown = 15 * time.Second
	}
	return &Breaker{
		failures:  map[string]int{},
		openUntil: map[string]time.Time{},
		threshold: threshold,
		cooldown:  cooldown,
		now:       time.Now,
	}
}

func (b *Breaker) Allow(backend string) (bool, string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if until, ok := b.openUntil[backend]; ok && b.now().Before(until) {
		return false, "circuit_open until " + until.UTC().Format(time.RFC3339)
	}
	return true, ""
}

func (b *Breaker) Success(backend string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.failures[backend] = 0
	delete(b.openUntil, backend)
}

func (b *Breaker) Failure(backend string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.failures[backend]++
	if b.failures[backend] >= b.threshold {
		b.openUntil[backend] = b.now().Add(b.cooldown)
	}
}
