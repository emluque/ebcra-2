# Base images are pinned to exact versions so a rebuild never silently reuses
# a stale locally-cached `latest`. Bump them deliberately (and keep the Go
# version in step with the `go` directive in ebcra-service/go.mod), then
# rebuild with `docker compose build --pull ebcra-service`.
FROM golang:1.27.3-alpine3.24 AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download && go mod verify

COPY . .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" -o /out/app .

# No extra packages: the binary is static and talks to Postgres with
# sslmode=disable, so it needs neither ca-certificates nor a bash/curl toolbox.
FROM alpine:3.24.3

RUN addgroup -S app && adduser -S -G app -H -h /app app

WORKDIR /app
COPY --from=builder /out/app ./app
# core.Init reads ./internal/core/core.json relative to the working directory.
COPY --from=builder /src/internal/core/core.json ./internal/core/core.json

USER app

CMD ["./app"]
