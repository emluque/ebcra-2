package status

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	"github.com/lib/pq"

	"github.com/emluque/ebcra-service-2.0/internal/cache"
	"github.com/emluque/ebcra-service-2.0/internal/config"
)

const cacheKey = "scrape_status"

// Dates are cut in Argentina's time zone so a late-evening run doesn't show
// up as the next day.
const localTZ = "America/Argentina/Buenos_Aires"

var acceptedClientIP string
var environment string

var src *cache.StringCache

var Con *sql.DB

type Row struct {
	TableName       string   `json:"table_name"`
	SourceKind      string   `json:"source_kind"`
	VariableID      *int64   `json:"variable_id,omitempty"`
	Status          string   `json:"status"`
	LastSuccessDate *string  `json:"last_success_date,omitempty"`
	CheckedDate     string   `json:"checked_date"`
	LastIngestDate  *string  `json:"last_ingested_date,omitempty"`
	SourceURL       *string  `json:"source_url,omitempty"`
	ErrorCode       *string  `json:"error_code,omitempty"`
	ErrorMessage    *string  `json:"error_message,omitempty"`
	CausedBy        []string `json:"caused_by,omitempty"`
}

func Init(cfg *config.Config) error {
	acceptedClientIP = cfg.ClientIP
	environment = cfg.Environment

	src = cache.New([]string{cacheKey})

	var err error
	Con, err = sql.Open("postgres", cfg.DSN())
	if err != nil {
		return fmt.Errorf("error opening PostgreSQL connection (status): %w", err)
	}
	if err = Con.Ping(); err != nil {
		return fmt.Errorf("error connecting to PostgreSQL database (status): %w", err)
	}
	log.Println("Successfully connected to PostgreSQL Database from Status.")
	return nil
}

func fetchStatuses() (string, error) {
	rows, err := Con.Query(
		`select table_name, source_kind, variable_id, status, last_success_date::text,
		        (checked_at at time zone $1)::date::text,
		        (last_ingested_at at time zone $1)::date::text,
		        source_url, error_code, error_message, caused_by
		 from scrape_status
		 order by table_name`,
		localTZ,
	)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	results := make([]*Row, 0)
	for rows.Next() {
		var (
			tableName, sourceKind, status, checkedDate          string
			variableID                                          sql.NullInt64
			lastSuccessDate, sourceURL, errorCode, errorMessage sql.NullString
			lastIngestDate                                      sql.NullString
			causedBy                                            pq.StringArray
		)
		if err := rows.Scan(
			&tableName, &sourceKind, &variableID, &status, &lastSuccessDate,
			&checkedDate, &lastIngestDate,
			&sourceURL, &errorCode, &errorMessage, &causedBy,
		); err != nil {
			return "", err
		}

		r := &Row{TableName: tableName, SourceKind: sourceKind, Status: status, CheckedDate: checkedDate}
		if variableID.Valid {
			r.VariableID = &variableID.Int64
		}
		if lastSuccessDate.Valid {
			r.LastSuccessDate = &lastSuccessDate.String
		}
		if lastIngestDate.Valid {
			r.LastIngestDate = &lastIngestDate.String
		}
		if sourceURL.Valid {
			r.SourceURL = &sourceURL.String
		}
		if errorCode.Valid {
			r.ErrorCode = &errorCode.String
		}
		if errorMessage.Valid {
			r.ErrorMessage = &errorMessage.String
		}
		if len(causedBy) > 0 {
			r.CausedBy = []string(causedBy)
		}
		results = append(results, r)
	}

	b, err := json.Marshal(&results)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func ResponseHandlerCreator() func(w http.ResponseWriter, r *http.Request) {
	handler := func(w http.ResponseWriter, r *http.Request) {

		if config.RemoteIP(r) != acceptedClientIP {
			http.Error(w, "Unauthorized Request", http.StatusForbidden)
			return
		}

		stringResults, hit := src.Get(cacheKey)

		if !hit {
			var err error
			stringResults, err = fetchStatuses()
			if err != nil {
				log.Printf("status: error fetching scrape_status: %v", err)
				errMsg := "Internal Server Error"
				if environment == "development" {
					errMsg = err.Error()
				}
				http.Error(w, errMsg, http.StatusInternalServerError)
				return
			}
			src.Set(cacheKey, stringResults)
		}

		w.Header().Set("Content-Type", "application/json; charset=UTF-8")
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, stringResults)
	}

	return handler
}

func CleanCache() {
	src.Flush()
}
