-- Applies one event to vessel_positions_current. The consumer reuses this statement.
--
-- It must do three things:
--   1. A vessel with no row yet gets one.
--   2. A newer event replaces every position column and refreshes updated_at.
--   3. A late or repeated event, whose event_time is not newer than the stored one,
--      changes nothing.
--
-- Use psycopg named parameters, for example %(mmsi)s, for these fields:
--   mmsi, event_time, latitude, longitude, speed_knots, course_degrees, nav_status
--
-- Prove it with: uv run --env-file .env pytest

INSERT INTO vessel_positions_current
    (mmsi, event_time, latitude, longitude, speed_knots, course_degrees, nav_status)
VALUES
    (%(mmsi)s, %(event_time)s, %(latitude)s, %(longitude)s, %(speed_knots)s, %(course_degrees)s, %(nav_status)s)
ON CONFLICT (mmsi) DO UPDATE
SET
    event_time = EXCLUDED.event_time, -- EXCLUDED is the row that I am trying to insert.
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    speed_knots = EXCLUDED.speed_knots,
    course_degrees = EXCLUDED.course_degrees,
    nav_status = EXCLUDED.nav_status,
    updated_at = NOW()
WHERE vessel_positions_current.event_time < EXCLUDED.event_time;