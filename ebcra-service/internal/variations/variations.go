package variations

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	_ "github.com/lib/pq"

	"github.com/emluque/ebcra-service-2.0/internal/config"
	"github.com/emluque/ebcra-service-2.0/internal/cache"
)

var acceptedClientIP string
var environment string

var src *cache.StringCache

var Con *sql.DB

func Init(cfg *config.Config) error {
	acceptedClientIP = cfg.ClientIP
	environment = cfg.Environment

	src = cache.New([]string{
		"var_base_res",
		"var_base",
		"var_base_usd",
		"var_res",
		"var_base_div_res",
		"var_depositos_por_tipo",
		"var_prestamos",
		"var_prestamos_por_tipo",
		"var_componentes",
		"var_merval",
		"var_merval_div_usd",
		"var_m2",
		"var_m2_usd",
		"var_m2_div_res",
		"var_pases",
		"var_m1",
		"var_m1_div_res",
		"var_m3",
		"var_m3_div_res",
		"var_depositos_usd",
		"var_depositos_sector",
		"var_liquidez_sistema_financiero",
		"var_comp_reservas",
		"var_depositos_titular",
		"var_hipotecarios_prendarios",
		"var_prestamos_titular",
	})

	var err error
	Con, err = sql.Open("postgres", cfg.DSN())
	if err != nil {
		return fmt.Errorf("error opening PostgreSQL connection (variations): %w", err)
	}
	if err = Con.Ping(); err != nil {
		return fmt.Errorf("error connecting to PostgreSQL database (variations): %w", err)
	}
	log.Println("Successfully connected to PostgreSQL Database from Variations.")
	return nil
}

var allowedProcedures = map[string]struct{}{
	"sp_ebcra_var_base_res":           {},
	"sp_ebcra_var_base":               {},
	"sp_ebcra_var_base_usd":           {},
	"sp_ebcra_var_res":                {},
	"sp_ebcra_var_base_div_res":       {},
	"sp_ebcra_var_depositos_por_tipo":    {},
	"sp_ebcra_var_prestamos":             {},
	"sp_ebcra_var_prestamos_por_tipo":    {},
	"sp_ebcra_var_componentes":        {},
	"sp_ebcra_var_merval":             {},
	"sp_ebcra_var_merval_div_usd":     {},
	"sp_ebcra_var_m2":                 {},
	"sp_ebcra_var_m2_usd":             {},
	"sp_ebcra_var_m2_div_res":                        {},
	"sp_ebcra_var_pases":                             {},
	"sp_ebcra_var_m1":                               {},
	"sp_ebcra_var_m1_div_res":                       {},
	"sp_ebcra_var_m3":                               {},
	"sp_ebcra_var_m3_div_res":                       {},
	"sp_ebcra_var_depositos_usd":                    {},
	"sp_ebcra_var_depositos_sector":                 {},
	"sp_ebcra_var_liquidez_sistema_financiero":      {},
	"sp_ebcra_var_comp_reservas":                    {},
	"sp_ebcra_var_depositos_titular":                {},
	"sp_ebcra_var_hipotecarios_prendarios":          {},
	"sp_ebcra_var_prestamos_titular":                {},
}

func callProcedureGetResults(procName string) (string, error) {
	log.Printf("callProcedureGetResults: %s", procName)

	if _, ok := allowedProcedures[procName]; !ok {
		return "", fmt.Errorf("callProcedureGetResults: unknown procedure %q", procName)
	}

	rows, err := Con.Query("SELECT * FROM " + procName + "()")
	if err != nil {
		return "", err
	}
	defer rows.Close()

	cols, err := rows.Columns()
	if err != nil {
		return "", err
	}

	pointers := make([]interface{}, len(cols))
	valuesContainer := make([]sql.NullString, len(cols))

	for i := range pointers {
		pointers[i] = &valuesContainer[i]
	}

	if !rows.Next() {
		return "", fmt.Errorf("callProcedureGetResults: no rows returned from %s", procName)
	}
	if err := rows.Scan(pointers...); err != nil {
		return "", err
	}

	results := make(map[string]string, len(cols)/2)
	for c := 0; c < len(cols); c = c + 2 {
		//First one is the date as string
		results[cols[c]] = valuesContainer[c].String
		results[cols[c+1]] = valuesContainer[c+1].String
	}

	b, err := json.Marshal(results)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func ResponseHandlerCreator(cacheKey string, procName string) func(w http.ResponseWriter, r *http.Request) {

	handler := func(w http.ResponseWriter, r *http.Request) {

		//verify IP
		if config.RemoteIP(r) != acceptedClientIP {
			http.Error(w, "Unauthorized Request", http.StatusForbidden)
			return
		}

		//Do Response
		stringResults, hit := src.Get(cacheKey)

		if !hit {
			//Cache miss
			var err error
			stringResults, err = callProcedureGetResults(procName)
			if err != nil {
				log.Printf("variations: error calling procedure %s: %v", procName, err)
				errMsg := "Internal Server Error"
				if environment == "development" {
					errMsg = err.Error()
				}
				http.Error(w, errMsg, http.StatusInternalServerError)
				return
			}
			src.Set(cacheKey, stringResults)
		}

		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, stringResults)
	}

	return handler
}

func CleanCache() {
	src.Flush()
}
