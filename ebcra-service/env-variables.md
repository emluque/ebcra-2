# Environment Variables

All configuration is provided via environment variables. There are no config files required at runtime.

## Variables

| Variable         | Required | Default           | Description                                                      |
|------------------|----------|-------------------|------------------------------------------------------------------|
| `ENVIRONMENT`    | No       | `production`      | Runtime environment. Use `development` or `production`. Controls CORS scheme (http vs https). |
| `PORT`           | No       | `8080`            | Port the HTTP server listens on.                                 |
| `DB_USER`        | **Yes**  | —                 | MySQL username.                                                  |
| `DB_PASSWORD`    | **Yes**  | —                 | MySQL password.                                                  |
| `DB_HOST`        | No       | `mysql`           | MySQL host.                                                      |
| `DB_PORT`        | No       | `3306`            | MySQL port.                                                      |
| `DB_NAME`        | No       | `estadisticasbcra`| MySQL database name.                                             |
| `JWT_SECRET`     | **Yes**  | —                 | Secret key used to sign and verify JWT tokens. Must be the same value across all instances. |
| `CLIENT_IP`      | No       | `172.30.1.10`     | IP address allowed to access variation endpoints and request JWT tokens (internal frontend). |
| `CLEAN_CACHE_IP` | No       | `172.30.1.12`     | IP address allowed to call `GET /clear_cache` (scraping service). |
| `PROMETHEUS_IP`  | No       | `172.30.1.101`    | IP address allowed to access `GET /metrics` (Prometheus server). `127.0.0.1` is always allowed. |

## docker-compose.yml example

```yaml
services:
  ebcra-service:
    image: ebcra-service:latest
    ports:
      - "8080:8080"
    environment:
      ENVIRONMENT: production
      PORT: 8080
      DB_HOST: mysql
      DB_PORT: 3306
      DB_USER: estadisticasbcra
      DB_PASSWORD: your_db_password_here
      DB_NAME: estadisticasbcra
      JWT_SECRET: your_jwt_secret_here
      CLIENT_IP: 172.30.1.10
      CLEAN_CACHE_IP: 172.30.1.12
      PROMETHEUS_IP: 172.30.1.101
    depends_on:
      - mysql

  mysql:
    image: mysql:8
    environment:
      MYSQL_DATABASE: estadisticasbcra
      MYSQL_USER: estadisticasbcra
      MYSQL_PASSWORD: your_db_password_here
      MYSQL_ROOT_PASSWORD: your_root_password_here
```

> **Security note:** Do not commit real secrets to version control. Use Docker secrets, a `.env` file excluded from git, or a secrets manager to supply `DB_PASSWORD` and `JWT_SECRET` in production.
