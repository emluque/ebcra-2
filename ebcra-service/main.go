package main

import (
	"fmt"
	"log"
	"net/http"

	"github.com/emluque/ebcra-service-2.0/internal/config"
	"github.com/emluque/ebcra-service-2.0/internal/core"
	jwtpkg "github.com/emluque/ebcra-service-2.0/internal/jwt"
	"github.com/emluque/ebcra-service-2.0/internal/variations"
)

func main() {

	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}

	coreRequestConf, err := core.Init(cfg)
	if err != nil {
		log.Fatal(err)
	}
	if err := variations.Init(cfg); err != nil {
		log.Fatal(err)
	}
	if err := jwtpkg.Init(cfg); err != nil {
		log.Fatal(err)
	}

	/* Core Service Handlers */
	for _, r := range coreRequestConf {

		// url, cacheKey, mysqlField, responseType
		http.HandleFunc(r[0], core.ResponseHandlerCreator(r[1], r[2], r[3], cfg.Environment))

	}

	http.HandleFunc("/metrics", core.MetricsHandler)

	/* End Core Service Handlers */

	/* Variations */
	//Stored procedures need a different mysql client

	http.HandleFunc("/var_base_res", variations.ResponseHandlerCreator("var_base_res", "sp_ebcra_var_base_res"))
	http.HandleFunc("/var_base", variations.ResponseHandlerCreator("var_base", "sp_ebcra_var_base"))
	http.HandleFunc("/var_base_usd", variations.ResponseHandlerCreator("var_base_usd", "sp_ebcra_var_base_usd"))
	http.HandleFunc("/var_res", variations.ResponseHandlerCreator("var_res", "sp_ebcra_var_res"))

	http.HandleFunc("/var_base_div_res", variations.ResponseHandlerCreator("var_base_div_res", "sp_ebcra_var_base_div_res"))

	http.HandleFunc("/var_depositos_por_tipo", variations.ResponseHandlerCreator("var_depositos_por_tipo", "sp_ebcra_var_depositos_por_tipo"))
	http.HandleFunc("/var_depositos_sector", variations.ResponseHandlerCreator("var_depositos_sector", "sp_ebcra_var_depositos_sector"))
	http.HandleFunc("/var_depositos_usd", variations.ResponseHandlerCreator("var_depositos_usd", "sp_ebcra_var_depositos_usd"))
	http.HandleFunc("/var_prestamos", variations.ResponseHandlerCreator("var_prestamos", "sp_ebcra_var_prestamos"))
	http.HandleFunc("/var_prestamos_por_tipo", variations.ResponseHandlerCreator("var_prestamos_por_tipo", "sp_ebcra_var_prestamos_por_tipo"))

	http.HandleFunc("/var_componentes", variations.ResponseHandlerCreator("var_componentes", "sp_ebcra_var_componentes"))

	http.HandleFunc("/var_merval", variations.ResponseHandlerCreator("var_merval", "sp_ebcra_var_merval"))
	http.HandleFunc("/var_merval_div_usd", variations.ResponseHandlerCreator("var_merval_div_usd", "sp_ebcra_var_merval_div_usd"))

	http.HandleFunc("/var_m2", variations.ResponseHandlerCreator("var_m2", "sp_ebcra_var_m2"))
	http.HandleFunc("/var_m2_usd", variations.ResponseHandlerCreator("var_m2_usd", "sp_ebcra_var_m2_usd"))
	http.HandleFunc("/var_m2_div_res", variations.ResponseHandlerCreator("var_m2_div_res", "sp_ebcra_var_m2_div_res"))

	http.HandleFunc("/var_pases", variations.ResponseHandlerCreator("var_pases", "sp_ebcra_var_pases"))

	http.HandleFunc("/var_m1",         variations.ResponseHandlerCreator("var_m1",         "sp_ebcra_var_m1"))
	http.HandleFunc("/var_m1_div_res", variations.ResponseHandlerCreator("var_m1_div_res", "sp_ebcra_var_m1_div_res"))
	http.HandleFunc("/var_m3",         variations.ResponseHandlerCreator("var_m3",         "sp_ebcra_var_m3"))
	http.HandleFunc("/var_m3_div_res", variations.ResponseHandlerCreator("var_m3_div_res", "sp_ebcra_var_m3_div_res"))

	http.HandleFunc("/var_liquidez_sistema_financiero", variations.ResponseHandlerCreator("var_liquidez_sistema_financiero", "sp_ebcra_var_liquidez_sistema_financiero"))

	http.HandleFunc("/var_comp_reservas", variations.ResponseHandlerCreator("var_comp_reservas", "sp_ebcra_var_comp_reservas"))

	http.HandleFunc("/var_depositos_titular", variations.ResponseHandlerCreator("var_depositos_titular", "sp_ebcra_var_depositos_titular"))
	http.HandleFunc("/var_hipotecarios_prendarios", variations.ResponseHandlerCreator("var_hipotecarios_prendarios", "sp_ebcra_var_hipotecarios_prendarios"))
	http.HandleFunc("/var_prestamos_titular", variations.ResponseHandlerCreator("var_prestamos_titular", "sp_ebcra_var_prestamos_titular"))

	/* End Variations */

	/* Clear both caches */
	http.HandleFunc("/clear_cache", cleanCachesHandlerFactory(cfg.CleanCacheIP))

	/* End Clear both caches */

	/* JWT */
	http.HandleFunc("/get-js-jwt", jwtpkg.FixedResponseHandlerCreator("javascript"))
	/* End JWT */

	log.Fatal(http.ListenAndServe(":"+cfg.Port, nil))

}

func cleanCachesHandlerFactory(cleanCacheIP string) func(w http.ResponseWriter, r *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {

		remoteIP := config.RemoteIP(r)

		xForwardedFor := r.Header.Get("X-Forwarded-For")

		if remoteIP != cleanCacheIP && xForwardedFor != cleanCacheIP {
			http.Error(w, "Unauthorized Request", http.StatusForbidden)
			return
		}

		log.Println("Cleared Cache")

		core.CleanCache()
		variations.CleanCache()

		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "Cache Cleared")
	}
}
