"""Schema, role and upsert behaviour, tested against a real PostgreSQL."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from psycopg import errors

UPSERT_CURRENT_POSITION = (
    Path(__file__).parent.parent / "database" / "upsert_current_position.sql"
).read_text()

INSERT_EVENT = """
    INSERT INTO vessel_events
        (mmsi, event_time, latitude, longitude, speed_knots, course_degrees, nav_status)
    VALUES
        (%(mmsi)s, %(event_time)s, %(latitude)s, %(longitude)s,
         %(speed_knots)s, %(course_degrees)s, %(nav_status)s)
    ON CONFLICT (mmsi, event_time) DO NOTHING
"""

MMSI = 235123456
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
TABLES = ["vessel_events", "vessel_positions_current"]


def event(**overrides) -> dict:
    return {
        "mmsi": MMSI,
        "event_time": T0,
        "latitude": 51.5,
        "longitude": 1.25,
        "speed_knots": 12.5,
        "course_degrees": 90.0,
        "nav_status": 0,
    } | overrides


def save(conn, values: dict) -> None:
    """Writes one event to both tables, the way the consumer will."""
    conn.execute(INSERT_EVENT, values)
    conn.execute(UPSERT_CURRENT_POSITION, values)


def history_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM vessel_events WHERE mmsi = %s", (MMSI,)).fetchone()[0]


def current_position(conn) -> dict:
    cursor = conn.execute(
        """
        SELECT mmsi, event_time, latitude, longitude, speed_knots, course_degrees, nav_status
        FROM vessel_positions_current
        WHERE mmsi = %s
        """,
        (MMSI,),
    )
    columns = [column.name for column in cursor.description]
    return dict(zip(columns, cursor.fetchone(), strict=True))


def test_duplicate_event_produces_one_history_row(writer):
    writer.execute(INSERT_EVENT, event())
    writer.execute(INSERT_EVENT, event())

    assert history_count(writer) == 1


def test_primary_key_rejects_a_duplicate_without_on_conflict(writer):
    insert = INSERT_EVENT.split("ON CONFLICT")[0]
    writer.execute(insert, event())

    with pytest.raises(errors.UniqueViolation):
        writer.execute(insert, event())


@pytest.mark.parametrize("statement", [INSERT_EVENT, UPSERT_CURRENT_POSITION], ids=TABLES)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mmsi", 12345),
        ("latitude", 90.1),
        ("latitude", -90.1),
        ("longitude", 180.1),
        ("longitude", -180.1),
        ("speed_knots", -1),
        ("course_degrees", 360),
        ("nav_status", 16),
    ],
)
def test_out_of_range_values_are_rejected(writer, statement, field, value):
    with pytest.raises(errors.CheckViolation):
        writer.execute(statement, event(**{field: value}))


def test_first_event_creates_the_current_position(writer):
    save(writer, event())

    assert current_position(writer) == event()


def test_newer_event_replaces_the_current_position(writer):
    newer = event(
        event_time=T0 + timedelta(minutes=5),
        latitude=52.0,
        longitude=2.5,
        speed_knots=7.5,
        course_degrees=45.0,
        nav_status=1,
    )
    save(writer, event())
    writer.execute("UPDATE vessel_positions_current SET updated_at = '2000-01-01'")

    save(writer, newer)

    assert current_position(writer) == newer
    updated_at = writer.execute(
        "SELECT updated_at FROM vessel_positions_current WHERE mmsi = %s", (MMSI,)
    ).fetchone()[0]
    assert updated_at.year > 2000


def test_late_event_enters_history_but_keeps_the_current_position(writer):
    latest = event()
    save(writer, latest)

    save(writer, event(event_time=T0 - timedelta(minutes=5), latitude=20.0))

    assert history_count(writer) == 2
    assert current_position(writer) == latest


def test_repeated_latest_event_changes_nothing(writer):
    save(writer, event())

    cursor = writer.execute(UPSERT_CURRENT_POSITION, event())

    assert cursor.rowcount == 0


@pytest.mark.parametrize("table", TABLES)
def test_reader_can_select(reader, table):
    reader.execute(f"SELECT count(*) FROM {table}")


@pytest.mark.parametrize("table", TABLES)
def test_reader_cannot_insert(reader, table):
    with pytest.raises(errors.InsufficientPrivilege):
        reader.execute(f"INSERT INTO {table} (mmsi) VALUES (%s)", (MMSI,))


def test_writer_cannot_update_history(writer):
    with pytest.raises(errors.InsufficientPrivilege):
        writer.execute("UPDATE vessel_events SET latitude = 0")


@pytest.mark.parametrize("table", TABLES)
def test_writer_cannot_delete(writer, table):
    with pytest.raises(errors.InsufficientPrivilege):
        writer.execute(f"DELETE FROM {table}")


@pytest.mark.parametrize("table", TABLES)
def test_writer_cannot_drop_tables(writer, table):
    with pytest.raises(errors.InsufficientPrivilege):
        writer.execute(f"DROP TABLE {table}")
