-- Runs once, when PostgreSQL initialises an empty data directory.
-- Editing this file does not change an existing database.

-- Append-only history: one row per distinct position report.
-- The primary key is the deduplication key, and it also serves
-- "history of one vessel over a time range" without a second index.
CREATE TABLE vessel_events (
    mmsi           INTEGER          NOT NULL CHECK (mmsi BETWEEN 100000000 AND 999999999),
    event_time     TIMESTAMPTZ      NOT NULL,
    latitude       DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude      DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    -- NULL means the vessel did not report the value.
    speed_knots    REAL             CHECK (speed_knots BETWEEN 0 AND 102.2),
    course_degrees REAL             CHECK (course_degrees >= 0 AND course_degrees < 360),
    nav_status     SMALLINT         CHECK (nav_status BETWEEN 0 AND 15),
    -- Compared with event_time, this shows how late each event arrived.
    ingested_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (mmsi, event_time)
);

-- Latest known position: one row per vessel, so the lookup stays fast
-- however long the history grows.
CREATE TABLE vessel_positions_current (
    mmsi           INTEGER          PRIMARY KEY CHECK (mmsi BETWEEN 100000000 AND 999999999),
    event_time     TIMESTAMPTZ      NOT NULL,
    latitude       DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude      DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    speed_knots    REAL             CHECK (speed_knots BETWEEN 0 AND 102.2),
    course_degrees REAL             CHECK (course_degrees >= 0 AND course_degrees < 360),
    nav_status     SMALLINT         CHECK (nav_status BETWEEN 0 AND 15),
    updated_at     TIMESTAMPTZ      NOT NULL DEFAULT now()
);

-- History is append-only, so the writer gets no UPDATE on it.
GRANT SELECT, INSERT         ON vessel_events            TO vessel_writer;
GRANT SELECT, INSERT, UPDATE ON vessel_positions_current TO vessel_writer;
GRANT SELECT ON vessel_events, vessel_positions_current  TO vessel_reader;
