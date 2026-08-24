package cache

import "sync"

type StringCache struct {
	mu    sync.RWMutex
	store map[string]string
}

func New(keys []string) *StringCache {
	c := &StringCache{store: make(map[string]string, len(keys))}
	for _, k := range keys {
		c.store[k] = ""
	}
	return c
}

func (c *StringCache) Get(key string) (string, bool) {
	c.mu.RLock()
	v := c.store[key]
	c.mu.RUnlock()
	return v, v != ""
}

func (c *StringCache) Set(key, value string) {
	c.mu.Lock()
	c.store[key] = value
	c.mu.Unlock()
}

func (c *StringCache) Flush() {
	c.mu.Lock()
	for k := range c.store {
		c.store[k] = ""
	}
	c.mu.Unlock()
}
