package jwt

import (
	"encoding/json"
	"net/http"
	"time"

	jwt "github.com/golang-jwt/jwt/v5"

	"github.com/emluque/ebcra-service-2.0/internal/config"
)

var jwtKey []byte
var acceptedClientIP string
var environment string

func Init(cfg *config.Config) error {
	jwtKey = cfg.JWTKey
	acceptedClientIP = cfg.ClientIP
	environment = cfg.Environment
	return nil
}

func FixedResponseHandlerCreator(user string) func(w http.ResponseWriter, r *http.Request) {

	handler := func(w http.ResponseWriter, r *http.Request) {

		remoteIP := config.RemoteIP(r)

		if remoteIP != acceptedClientIP {
			msg := "Unauthorized Request"
			if environment == "development" {
				msg += " --- " + remoteIP
			}
			http.Error(w, msg, http.StatusForbidden)
			return
		}

		token := jwt.New(jwt.SigningMethodHS512)
		claims := make(jwt.MapClaims)
		claims["exp"] = time.Now().Add(time.Hour * 24).Unix()
		claims["user"] = user
		claims["type"] = "web"
		token.Claims = claims

		tokenString, err := token.SignedString(jwtKey)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		jsonResponse := make(map[string]string)
		jsonResponse["token"] = tokenString

		b, err := json.Marshal(jsonResponse)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json; charset=UTF-8")
		w.WriteHeader(http.StatusOK)
		w.Write(b)

	}

	return handler

}
