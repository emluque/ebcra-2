package config

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
)

type Config struct {
	Environment  string
	Port         string
	CleanCacheIP string
	PrometheusIP string
	ClientIP     string
	JWTKey       []byte
	DBUser       string
	DBPassword   string
	DBHost       string
	DBPort       string
	DBName       string
}

func getOrDefault(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}

func RemoteIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func (c *Config) DSN() string {
	return fmt.Sprintf("host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		c.DBHost, c.DBPort, c.DBUser, c.DBPassword, c.DBName)
}

func Load() (*Config, error) {
	jwtSecret := os.Getenv("JWT_SECRET")
	if jwtSecret == "" {
		return nil, errors.New("JWT_SECRET environment variable is required")
	}
	dbUser := os.Getenv("DB_USER")
	if dbUser == "" {
		return nil, errors.New("DB_USER environment variable is required")
	}
	dbPassword := os.Getenv("DB_PASSWORD")
	if dbPassword == "" {
		return nil, errors.New("DB_PASSWORD environment variable is required")
	}
	cleanCacheIP := os.Getenv("CLEAN_CACHE_IP")
	if cleanCacheIP == "" {
		return nil, errors.New("CLEAN_CACHE_IP environment variable is required")
	}
	prometheusIP := os.Getenv("PROMETHEUS_IP")
	if prometheusIP == "" {
		return nil, errors.New("PROMETHEUS_IP environment variable is required")
	}
	clientIP := os.Getenv("CLIENT_IP")
	if clientIP == "" {
		return nil, errors.New("CLIENT_IP environment variable is required")
	}
	return &Config{
		Environment:  getOrDefault("ENVIRONMENT", "production"),
		Port:         getOrDefault("PORT", "8080"),
		CleanCacheIP: cleanCacheIP,
		PrometheusIP: prometheusIP,
		ClientIP:     clientIP,
		JWTKey:       []byte(jwtSecret),
		DBUser:       dbUser,
		DBPassword:   dbPassword,
		DBHost:       getOrDefault("DB_HOST", "postgres"),
		DBPort:       getOrDefault("DB_PORT", "5432"),
		DBName:       getOrDefault("DB_NAME", "estadisticasbcra"),
	}, nil
}
