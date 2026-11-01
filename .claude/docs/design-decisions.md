# Design decisions

Every meaningful technical choice is recorded here, with the alternatives and the reasons.

## 1. Kafka between the producer and PostgreSQL

**Decision:** events pass through Kafka instead of being written directly to PostgreSQL.

**Context:** vessels report continuously. Events arrive in bursts, duplicated and out of order, and more than one system needs to read them.

**Alternatives:**
- The producer writes straight to PostgreSQL.
- A traditional queue such as RabbitMQ, which normally removes a message once it is acknowledged, so it cannot be replayed.
- PostgreSQL as a queue with `FOR UPDATE SKIP LOCKED`, which is simple but ties ingestion to one database.

**Reasons:**
- **Decoupling:** the producer does not need to know who reads events, or whether the database is up.
- **Buffering:** during a burst or an outage, events wait in Kafka and consumers catch up.
- **Replay:** retained events can be read again after a bug fix.
- **Independent consumers:** each consumer group tracks its own position in the topic.
- **Ordering:** events with the same key stay in order within a partition.

**Trade-offs:** Kafka adds a system to run and monitor. Reads are eventually consistent with writes, and at-least-once delivery means consumers must handle duplicates.

**At scale:** three or more brokers across availability zones, replication factor 3, `min.insync.replicas=2` and `acks=all`, probably on a managed service such as Amazon MSK.

## 2. Two consumer groups instead of a dual write

**Decision:** one consumer group writes to PostgreSQL and a separate archiver group writes to raw storage. No single process writes to both.

**Context:** the original diagram showed one consumer feeding both stores.

**Alternatives:**
- One consumer writes to both, which is simpler to run.
- A transactional outbox in PostgreSQL, which is reliable but makes the archive depend on the database.

**Reasons:**
- A process that writes to two systems can crash between them, leaving one with data the other lacks. With two groups, each sink commits its own offset and recovers on its own.
- The archive stores events before validation, so it stays a true record. If validation had a bug, the originals can be reprocessed.
- A slow or failed sink does not hold up the other.

**Trade-offs:** there is one more service to deploy and monitor, and the two stores can lag each other for a while. A reconciliation check covers that gap.

**At scale:** Kafka Connect with an S3 sink would replace the custom archiver.

## 3. Natural key `(mmsi, event_time)` for deduplication

**Decision:** an event's identity is its vessel and timestamp, enforced as the primary key of `vessel_events`.

**Context:** AIS reports have no shared message ID, and one transmission can reach several receivers. A producer-generated UUID would give each received copy a different ID, so duplicates would survive.

**Alternatives:**
- A UUID per event, which only catches redelivery of the exact same message.
- A hash of the payload, which treats any small difference between receivers as a new event.
- A surrogate key plus a separate unique index, which adds a second index for no benefit here.

**Reasons:**
- It matches what a duplicate really is in this domain.
- One index does two jobs: deduplication and "history of one vessel over a time range".
- PostgreSQL requires a unique key on a partitioned table to include the partition column. This key already includes `event_time`, so partitioning needs no redesign.

**Trade-offs:** if two genuinely different reports share a vessel and timestamp, the first one wins. That is acceptable at one-second resolution, and the raw archive still holds both.

**At scale:** the same key works on a table partitioned by time.

## 4. Separate history and current-position tables, with no dimension table

**Decision:** `vessel_events` is append-only history. `vessel_positions_current` holds one row per vessel. Both are updated in one transaction.

**Context:** the two main queries have very different shapes. "Where is this vessel now?" must stay fast however long the history grows.

**Alternatives:**
- One table with `SELECT DISTINCT ON (mmsi)`, whose cost grows with the history.
- A materialized view, which is stale between refreshes and costly to refresh often.
- A vessel dimension table with foreign keys, which nothing needs yet. It would also force ordering between static vessel data and position events.

**Reasons:**
- Primary-key lookup on the current table is constant-time in practice, regardless of history size.
- History stays immutable and the current table stays small, so each can be tuned for its own workload.
- A late event can safely enter history while a guard keeps it out of the current position.

**Trade-offs:** each event causes two writes, and the current table is derived data that could be wrong if the logic is. It can always be rebuilt from history.

**At scale:** add a vessel dimension without foreign keys on events, partition history by time, add PostGIS for geographic queries, and possibly cache current positions.

## 5. `.env` locally, secrets manager in production

**Decision:** services read configuration from environment variables. Locally those come from a git-ignored `.env`. In production a secrets manager would inject the same variables.

**Context:** credentials must not be in the repo, the images or the Compose file.

**Alternatives:**
- Docker secrets, which mount values as files. They are good, but need file-reading code in each service and do not carry over to every platform.
- Hard-coded development defaults, which tend to reach production.

**Reasons:**
- Code does not change between environments. Only the source of the variables does.
- `${VAR:?}` makes Compose fail immediately when a value is missing, instead of starting with a blank password.
- `scripts/create-env.sh` generates random values, so there are no shared passwords, and CI creates new ones on every run.

**Trade-offs:** environment variables are visible to anyone who can inspect the container. That is acceptable locally but one reason to prefer short-lived credentials in production.

**At scale:** AWS Secrets Manager with automatic rotation, or IAM database authentication in place of passwords.

## 6. Least-privilege database roles

**Decision:** the superuser only initialises the database. The consumer connects as `vessel_writer` and the API as `vessel_reader`.

**Context:** a bug or compromise in a service should be limited to what that service needs.

**Alternatives:** one shared application role, which is simpler but gives the read-only API the power to change data.

**Reasons:**
- The API cannot modify data even if it has an injection bug.
- `vessel_writer` has no `UPDATE` or `DELETE` on `vessel_events`, so the database itself enforces append-only history.
- Neither role owns the tables, so neither can drop them.

**Trade-offs:** there are more credentials to manage, and every new table needs explicit grants.

**At scale:** one role per service, with rotation handled by the secrets manager.

## 7. `init.sql` for now, a migration tool in production

**Decision:** the schema lives in `database/init.sql`, which PostgreSQL runs on first start.

**Context:** the image only runs init scripts against an empty data directory. Editing the file later does nothing to an existing database.

**Alternatives:** Alembic or Flyway, which track versioned migrations.

**Reasons:** while the data is synthetic and disposable, the schema can change by recreating the volume, so a migration tool would add setup without adding safety.

**Trade-offs:** there is no upgrade path for a database that must keep its data. Local schema changes need `docker compose down -v`.

**At scale:** versioned migrations applied by the deployment pipeline, written to be backward compatible so old and new code can run side by side.

## 8. uv instead of pip or Poetry

**Decision:** uv manages Python 3.12, the dependencies and the lock file.

**Context:** the machine's system Python is 3.8, which is end-of-life, and the operating system depends on it, so it cannot be replaced.

**Alternatives:**
- `pip` with `requirements.txt`, which has no lock file of its own and no Python version management.
- `pip-tools`, which adds locking but still needs a separate Python manager.
- Poetry, which is capable but slower and does not install Python itself.

**Reasons:**
- One tool replaces pip, venv and pyenv, and installs Python beside the system version without touching it.
- `uv.lock` pins the full dependency tree with hashes, so CI and images install exactly what was tested.
- A uv workspace gives every service one shared lock file.

**Trade-offs:** uv is younger than pip and comes from a single vendor, and its lock file is specific to uv. `uv export` can produce a `requirements.txt` if the project ever needs to leave.

**At scale:** the same approach, with a private package index and pinned uv versions in build images.

## 9. Branch-per-environment promotion

**Decision:** work moves through `feature/*`, `dev`, `sit`, `uat` and `main`, by pull request, with CI gates at each step.

**Context:** this mirrors the controlled release flow many organisations use, where test stages and approvals sit between development and production.

**Alternatives:** trunk-based development, with short-lived branches, one main branch, and feature flags to separate deployment from release.

**Reasons:**
- Each stage has a visible state and its own gates.
- A ruleset blocks direct pushes, and the `prod` environment adds a manual approval.
- A path check allows only the expected promotions, so nothing can skip a stage.

**Trade-offs:**
- Long-lived branches can drift, especially if a fix lands on one and not the others. This is the main reason many teams prefer trunk-based development.
- Promotions must use merge commits. A squash creates a new commit that the source branch does not contain, so every later promotion would hit false conflicts. The repository therefore allows merge commits only.
- With a solo developer, GitHub cannot require PR approvals because you cannot approve your own PR. The approval gate is the `prod` environment instead.

**At scale:** build one image and promote that same image through each stage, so what was tested is what ships. Each environment would be a separate cloud account.
