# Postgres Connection Note

The user already runs Postgres+pgvector in Docker. No docker-compose.yml is provided
because spinning up a second container would conflict with the existing one.

## Confirmed connection details

| Parameter | Value |
|-----------|-------|
| Host | `localhost` (127.0.0.1) |
| Port | `5432` |
| Database | `vectordb` |
| Username | `admin` |
| Password | `password` |
| Extension | `pgvector` available |

## Verify manually

```bash
psql postgresql://admin:password@localhost:5432/vectordb -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```

## If you need to start Postgres fresh

```bash
docker run -d \
  --name pgvector \
  -e POSTGRES_USER=admin \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=vectordb \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```
