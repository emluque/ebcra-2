# First-time Setup

Complete steps to provision a new host and get the stack running.

## Prerequisites

Docker and Docker Compose must be installed.

## 1. Create host directories

```bash
mkdir -p /home/data/postgres /home/data/nginx-logs
sudo chown -R 999:root /home/data/postgres
sudo chown -R www-data:www-data /home/data/nginx-logs
```

## 2. Start PostgreSQL

```bash
sudo docker compose up -d postgres
```

Wait a few seconds for it to initialize.

## 3. Initialize database schema and users

```bash
sudo docker exec -i -e PGPASSWORD=postgres-password postgres psql -U postgres -f - < setup/postgres/setup.sql
```

## 4. Restore from full dump

A dated full dump lives at `setup/postgres/*.estadisticasbcra.sql`.

```bash
sudo docker exec -i -e PGPASSWORD=postgres-password postgres \
    psql -U postgres -d estadisticasbcra -f - < setup/postgres/<dump-file>.estadisticasbcra.sql
```

## 5. Build and start all services

```bash
sudo docker compose up -d --build
```

## 6. Configure /etc/hosts

Add the following entries so the domains resolve locally:

```
127.0.0.1 estadisticasbcra.com
127.0.0.1 api.estadisticasbcra.com
```

## Verification

```bash
# All 5 containers should be running
sudo docker compose ps

# Web frontend
curl http://estadisticasbcra.com

# Go API
curl http://api.estadisticasbcra.com

# DB has data
sudo docker exec -it postgres psql -U postgres -c "\l"
```
