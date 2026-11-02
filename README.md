# Marine Vessel Intelligence Pipeline

A local, containerised data engineering project. Synthetic vessel position events flow through Kafka into PostgreSQL and a raw archive, with Airflow running backfills and data-quality checks and FastAPI serving the results.

The project is being built in stages. **PostgreSQL, the schema and the CI gates exist today.** The other components in [the architecture](.claude/docs/architecture.md) follow.

## Prerequisites

- Docker with Compose v2
- [uv](https://docs.astral.sh/uv/), which installs the pinned Python version itself

## Run it

```bash
scripts/create-env.sh                # creates .env with random passwords
docker compose up -d --wait          # starts PostgreSQL and waits until it is healthy
uv sync                              # installs Python 3.12 and the locked dependencies
uv run --env-file .env pytest        # tests the schema, roles and upsert
```

`docker compose down` stops the stack and keeps the data. Adding `-v` also deletes the data.

## Branches

Work moves through `feature/*`, `dev`, `sit`, `uat` and `main`, by pull request only. Each step has to pass the gates in [ci.yml](.github/workflows/ci.yml), and `main` also needs a manual approval.

## Documentation

- [Architecture](.claude/docs/architecture.md)
- [Design decisions](.claude/docs/design-decisions.md)
