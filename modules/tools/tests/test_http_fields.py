"""HTTP date/seconds examples and deterministic clocks, independent of providers."""

from datetime import datetime, timedelta, timezone

import pytest

from modules.tools.components.http import parse_retry_after


@pytest.mark.parametrize(
    "value",
    [
        "Sun, 06 Nov 1994 08:49:37 GMT",
        "Sunday, 06-Nov-94 08:49:37 GMT",
        "Sun Nov  6 08:49:37 1994",
    ],
)
def test_http_date_forms_use_the_supplied_instant_and_gmt(value):
    now = datetime(1994, 11, 6, 8, 47, 37, tzinfo=timezone.utc)
    assert parse_retry_after(value, now=now) == 120
    assert parse_retry_after(value, now=now.astimezone(timezone(timedelta(hours=-5)))) == 120
    assert parse_retry_after(value, now=now + timedelta(minutes=3)) == 0


@pytest.mark.parametrize("value,expected", [("120", 120), ("0", 0), (" 00120 ", 120)])
def test_decimal_seconds(value, expected):
    assert parse_retry_after(value, now=datetime(2026, 11, 21, tzinfo=timezone.utc)) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "NaN",
        "inf",
        "-1",
        "+60",
        "1.5",
        "1e3",
        "١٢٠",
        "9" * 129,
        "Sun, 06 Nov 1994 08:49:37",
        "not a date",
    ],
)
def test_missing_or_invalid_guidance_remains_distinguishable_from_zero(value):
    assert parse_retry_after(value, now=datetime(2026, 11, 21, tzinfo=timezone.utc)) is None


def test_naive_clock_is_a_caller_error_not_invalid_server_guidance():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_retry_after("120", now=datetime(2026, 11, 21))
