package core

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"

	_ "github.com/lib/pq"
	jwt "github.com/golang-jwt/jwt/v5"

	"github.com/emluque/ebcra-service-2.0/internal/cache"
	"github.com/emluque/ebcra-service-2.0/internal/config"
)

var prometheusServerIP string

var Con *sql.DB

var jwtKey []byte

var ServiceRequests int64
var ServiceUnauthorizedRequests int64

type IntResult struct {
	Date  string `json:"d"`
	Value int    `json:"v"`
}

type FloatResult struct {
	Date  string  `json:"d"`
	Value float64 `json:"v"`
}

type MilestonesResult struct {
	Date  string `json:"d"`
	Event string `json:"e"`
	Type  string `json:"t"`
}

var src *cache.StringCache

func Init(cfg *config.Config) ([][]string, error) {
	prometheusServerIP = cfg.PrometheusIP
	jwtKey = cfg.JWTKey

	data, err := os.ReadFile("./internal/core/core.json")
	if err != nil {
		return nil, err
	}

	var coreRequestConf [][]string
	if err = json.Unmarshal(data, &coreRequestConf); err != nil {
		return nil, err
	}

	keys := make([]string, 0, len(coreRequestConf))
	for _, r := range coreRequestConf {
		mysqlField := r[2]
		for _, c := range mysqlField {
			if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_') {
				return nil, fmt.Errorf("core.json: unsafe table name %q", mysqlField)
			}
		}
		keys = append(keys, r[1])
		log.Println("Establishing cache for: " + r[1])
	}
	src = cache.New(keys)

	Con, err = sql.Open("postgres", cfg.DSN())
	if err != nil {
		return nil, fmt.Errorf("error opening PostgreSQL connection: %w", err)
	}
	if err = Con.Ping(); err != nil {
		return nil, fmt.Errorf("error connecting to PostgreSQL database: %w", err)
	}
	log.Println("Successfully connected to PostgreSQL Database.")
	return coreRequestConf, nil
}

func milestonesStringResultsBuilder(rows *sql.Rows) (string, error) {
	results := make([]*MilestonesResult, 0)
	var d, e, t string
	for rows.Next() {
		err := rows.Scan(&d, &e, &t)
		if err != nil {
			return "", err
		}

		results = append(results, &MilestonesResult{d, e, t})
	}
	b, err := json.Marshal(&results)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func intStringResultsBuilder(rows *sql.Rows) (string, error) {
	results := make([]*IntResult, 0)
	var d, vo string
	for rows.Next() {
		err := rows.Scan(&d, &vo)
		if err != nil {
			return "", err
		}

		v, err := strconv.Atoi(vo)
		if err != nil {
			return "", err
		}
		results = append(results, &IntResult{d, v})
	}

	b, err := json.Marshal(&results)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func floatStringResultsBuilder(rows *sql.Rows) (string, error) {
	results := make([]*FloatResult, 0)
	var d, vo string
	for rows.Next() {
		err := rows.Scan(&d, &vo)
		if err != nil {
			return "", err
		}

		v, err := strconv.ParseFloat(vo, 64)
		if err != nil {
			return "", err
		}
		results = append(results, &FloatResult{d, v})
	}

	b, err := json.Marshal(&results)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func setCORSHeaders(w http.ResponseWriter, r *http.Request, environment string) {
	w.Header().Set("Content-Type", "application/json; charset=UTF-8")
	w.Header().Set("Access-Control-Allow-Credentials", "true")
	w.Header().Set("Access-Control-Expose-Headers", "FooBar")
	w.Header().Set("Access-Control-Allow-Headers", "Authorization")

	requestOrigin := r.Header.Get("Origin")
	if environment == "development" {
		if requestOrigin == "http://www.estadisticasbcra.com" {
			w.Header().Set("Access-Control-Allow-Origin", "http://www.estadisticasbcra.com")
		} else {
			w.Header().Set("Access-Control-Allow-Origin", "http://estadisticasbcra.com")
		}
	} else {
		if requestOrigin == "https://www.estadisticasbcra.com" {
			w.Header().Set("Access-Control-Allow-Origin", "https://www.estadisticasbcra.com")
		} else {
			w.Header().Set("Access-Control-Allow-Origin", "https://estadisticasbcra.com")
		}
	}
}

func dbError(err error, environment string) string {
	if environment == "development" {
		return err.Error()
	}
	return "Internal Server Error"
}

func ResponseHandlerCreator(cacheKey string, mysqlField string, responseType string, environment string) func(w http.ResponseWriter, r *http.Request) {

	handler := func(w http.ResponseWriter, r *http.Request) {

		var err error

		//CORS
		if r.Method == "OPTIONS" {
			setCORSHeaders(w, r, environment)
			w.WriteHeader(http.StatusOK)
			return
		}

		//Verify Token
		authorizationHeader := r.Header.Get("Authorization")

		if len(authorizationHeader) < 10 {
			http.Error(w, "Unauthorized Request: No Access Token", http.StatusForbidden)
			atomic.AddInt64(&ServiceUnauthorizedRequests, 1)
			return
		}

		tokenString := authorizationHeader[7:]

		token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
			}
			return jwtKey, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, "Unauthorized Request: Invalid Token", http.StatusForbidden)
			atomic.AddInt64(&ServiceUnauthorizedRequests, 1)
			return
		}

		//Do Response
		var stringResults string

		stringResults, hit := src.Get(cacheKey)

		if !hit {

			//Cache miss
			var rows *sql.Rows
			switch responseType {
			case "int", "float":
				rows, err = Con.Query(`select "date"::text as d, value::text as v from ` + mysqlField + ` order by "date"`)
			case "milestones":
				rows, err = Con.Query(`select "date"::text as d, event::text as e, "type"::text as t from milestones order by "date", "type"`)
			}

			if err != nil {
				log.Printf("%s : %s :: Error: %s", r.Method, r.RequestURI, err.Error())
				http.Error(w, dbError(err, environment), http.StatusInternalServerError)
				return
			}
			defer rows.Close()

			switch responseType {
			case "int":
				stringResults, err = intStringResultsBuilder(rows)
			case "float":
				stringResults, err = floatStringResultsBuilder(rows)
			case "milestones":
				stringResults, err = milestonesStringResultsBuilder(rows)
			}
			if err != nil {
				log.Printf("%s : %s :: Error: %s", r.Method, r.RequestURI, err.Error())
				http.Error(w, dbError(err, environment), http.StatusInternalServerError)
				return
			}

			src.Set(cacheKey, stringResults)

		}

		atomic.AddInt64(&ServiceRequests, 1)

		setCORSHeaders(w, r, environment)
		w.WriteHeader(http.StatusOK)

		fmt.Fprint(w, stringResults)

	}

	return handler
}

func CleanCache() {
	src.Flush()
}

func MetricsHandler(w http.ResponseWriter, r *http.Request) {

	remoteIP := config.RemoteIP(r)

	if remoteIP != "127.0.0.1" && remoteIP != prometheusServerIP {
		http.Error(w, "Unauthorized Request", http.StatusForbidden)
		return
	}

	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, "ebcraCoreServiceRequests %d\n", atomic.LoadInt64(&ServiceRequests))
	fmt.Fprintf(w, "ebcraCoreServiceUnauthorizedRequests %d\n", atomic.LoadInt64(&ServiceUnauthorizedRequests))
}
