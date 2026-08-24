FROM golang:latest AS builder

WORKDIR /

COPY go.mod go.sum ./
RUN go mod download

COPY / .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o app

FROM alpine:latest
RUN apk --no-cache add \
    ca-certificates \
    bash \
    curl

WORKDIR /root/
COPY --from=builder /app .
RUN mkdir -p internal
RUN mkdir -p internal/core
COPY --from=builder /internal/core/core.json ./internal/core/core.json


CMD ["./app"]
