from lsio_api.dates import parse_iso, python_timestamp


def test_python_timestamp() -> None:
    assert python_timestamp("2026-10-24T11:25:58Z") == "2026-10-24 11:25:58+00:00"
    assert python_timestamp("2026-10-24T11:25:58.123Z") == "2026-10-24 11:25:58+00:00"
    assert python_timestamp(None) == ""
    assert python_timestamp("nonsense") == ""


def test_parse_iso_reads_both_formats() -> None:
    assert parse_iso("2026-10-24T11:25:58Z") == parse_iso("2026-10-24 11:25:58+00:00")
    assert parse_iso("") is None
    assert parse_iso(None) is None
