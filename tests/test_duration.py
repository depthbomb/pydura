import pickle
import pytest
from hypothesis import given
from zoneinfo import ZoneInfo
from operator import add, mul, sub
from hypothesis import strategies as st
from dataclasses import FrozenInstanceError
from pydura import Duration, format_duration, parse
from datetime import UTC, datetime, timedelta, timezone


def test_constructor_and_value_protocols() -> None:
    value = Duration(
        weeks=1,
        days=-7,
        hours=1,
        minutes=2,
        seconds=3,
        milliseconds=4,
        microseconds=5,
        nanoseconds=6,
    )
    assert value == parse('1h2m3s4ms5us6ns')
    assert value.nanoseconds == 3_723_004_005_006
    assert value.total_seconds() == 3_723.004005006
    assert repr(Duration(nanoseconds=7)) == 'Duration(nanoseconds=7)'
    assert bool(value)
    assert not Duration()
    assert len({value, parse(str(value))}) == 1
    assert sorted([value, Duration(), -value]) == [-value, Duration(), value]
    assert value != 3_723_004_005_006
    assert Duration(seconds=1) != timedelta(seconds=1)
    assert pickle.loads(pickle.dumps(value)) == value
    with pytest.raises(FrozenInstanceError):
        value.nanoseconds = 2


@pytest.mark.parametrize(
    'unit',
    ['weeks', 'days', 'hours', 'minutes', 'seconds', 'milliseconds', 'microseconds', 'nanoseconds'],
)
@pytest.mark.parametrize('value', [True, 1.5, '1', None])
def test_constructor_rejects_non_integer_units(unit: str, value: object) -> None:
    with pytest.raises(TypeError, match=f'{unit} must be an int'):
        Duration(**{unit: value})


def test_arithmetic() -> None:
    hour = Duration(hours=1)
    half = timedelta(minutes=30)
    assert hour + hour == Duration(hours=2)
    assert hour - hour == Duration()
    assert hour + half == half + hour == Duration(minutes=90)
    assert hour - half == Duration(minutes=30)
    assert half - hour == Duration(minutes=-30)
    assert hour * 2 == 2 * hour == Duration(hours=2)
    assert hour * -2 == Duration(hours=-2)
    assert hour * 0 == Duration()
    assert abs(-hour) == hour
    assert +hour is hour


@pytest.mark.parametrize('operation', [add, sub, mul])
@pytest.mark.parametrize('other', [None, '1h', 1.5, True])
def test_unsupported_arithmetic(operation, other: object) -> None:
    with pytest.raises(TypeError):
        operation(Duration(seconds=1), other)

    with pytest.raises(TypeError):
        operation(other, Duration(seconds=1))


@given(st.timedeltas())
def test_timedelta_conversion_round_trip(value: timedelta) -> None:
    assert Duration.from_timedelta(value).to_timedelta() == value


@pytest.mark.parametrize('nanoseconds', [1, 999, 1_001, -1, -999, -1_001])
def test_loss_of_precision_is_explicit(nanoseconds: int) -> None:
    value = Duration(nanoseconds=nanoseconds)
    with pytest.raises(ValueError, match='sub-microsecond'):
        value.to_timedelta()

    expected = abs(nanoseconds) // 1_000 * (-1 if nanoseconds < 0 else 1)
    assert value.to_timedelta(truncate=True) == timedelta(microseconds=expected)


def test_datetime_integration() -> None:
    for base in (datetime(2026, 8, 23, 12), datetime(2026, 8, 23, 12, tzinfo=UTC)):
        value = parse('1d3h15m3s')
        expected = base + timedelta(days=1, hours=3, minutes=15, seconds=3)
        assert base + value == value + base == value.add_to(base) == expected
        assert expected - value == base
        with pytest.raises(ValueError, match='sub-microsecond'):
            _ = base + Duration(nanoseconds=1)

        with pytest.raises(ValueError, match='sub-microsecond'):
            _ = base - Duration(nanoseconds=1)

        assert Duration(nanoseconds=1).add_to(base, truncate=True) == base


@pytest.mark.parametrize(
    ('base', 'expected'),
    [
        (datetime(2026, 3, 7, 12), datetime(2026, 3, 8, 13)),
        (datetime(2026, 10, 31, 12), datetime(2026, 11, 1, 11)),
    ],
)
def test_elapsed_days_across_dst(base: datetime, expected: datetime) -> None:
    zone = ZoneInfo('America/New_York')
    start = base.replace(tzinfo=zone)
    result = start + Duration(days=1)
    assert result == expected.replace(tzinfo=zone)
    assert result.tzinfo is zone
    assert result.timestamp() - start.timestamp() == 86_400
    assert result - Duration(days=1) == start


def test_fall_back_fold_is_preserved() -> None:
    zone = ZoneInfo('America/New_York')
    start = datetime(2026, 11, 1, 1, 30, tzinfo=zone)
    result = start + Duration(hours=1)
    assert result.hour == 1
    assert result.fold == 1
    assert result.timestamp() - start.timestamp() == 3_600


def test_standard_library_range_limits() -> None:
    with pytest.raises(OverflowError):
        Duration(days=1_000_000_000).to_timedelta()

    with pytest.raises(OverflowError):
        _ = datetime.max + Duration(seconds=1)


def test_conversion_type_errors() -> None:
    with pytest.raises(TypeError, match='value must be a timedelta'):
        Duration.from_timedelta(1)

    with pytest.raises(TypeError, match='base must be a datetime'):
        Duration().add_to('now')

    with pytest.raises(TypeError, match='truncate must be a bool'):
        Duration().to_timedelta(truncate=1)


@pytest.mark.parametrize(
    ('value', 'text'),
    [
        (Duration(), '0 milliseconds'),
        (Duration(nanoseconds=1), '1 nanosecond'),
        (Duration(nanoseconds=-1), '-1 nanosecond'),
        (Duration(microseconds=500), '500 microseconds'),
        (
            Duration(milliseconds=1, microseconds=500, nanoseconds=3),
            '1 millisecond 500 microseconds 3 nanoseconds',
        ),
        (Duration(microseconds=-1501), '-1 millisecond 501 microseconds'),
        (
            timedelta(hours=1, minutes=1, seconds=1, milliseconds=1),
            '1 hour 1 minute 1 second 1 millisecond',
        ),
        (Duration(days=365 + 60 + 21 + 4), '1 year 2 months 3 weeks 4 days'),
    ],
)
def test_format(value: Duration | timedelta, text: str) -> None:
    assert format_duration(value) == text


def test_format_limit_counts_nonzero_units() -> None:
    value = parse('-1d15m3s')
    assert format_duration(value, max_units=2) == '-1 day 15 minutes'
    assert format_duration(value, max_units=1) == '-1 day'
    assert format_duration(value, max_units=10) == str(value)
    assert format_duration(Duration(), max_units=1) == '0 milliseconds'


@pytest.mark.parametrize('limit', [0, -1])
def test_format_rejects_nonpositive_limit(limit: int) -> None:
    with pytest.raises(ValueError, match='max_units must be positive'):
        format_duration(Duration(), max_units=limit)


@pytest.mark.parametrize('limit', [True, 1.5, '2'])
def test_format_rejects_non_integer_limit(limit: object) -> None:
    with pytest.raises(TypeError, match='max_units must be an int'):
        format_duration(Duration(), max_units=limit)


@pytest.mark.parametrize('value', [1, '1h', None])
def test_format_requires_explicit_duration_units(value: object) -> None:
    with pytest.raises(TypeError, match='value must be a Duration or timedelta'):
        format_duration(value)


def test_reflected_multiplication_does_not_swap_foreign_operands() -> None:
    class Foreign:
        def __mul__(self, other):
            return NotImplemented

        def __rmul__(self, other):
            pytest.fail('Duration must not retry the expression with swapped operands')

    value = Duration(seconds=1)
    assert value.__rmul__(Foreign()) is NotImplemented
    with pytest.raises(TypeError):
        _ = Foreign() * value


@pytest.mark.parametrize('offset', [timedelta(hours=1), timedelta(hours=-1)])
@pytest.mark.parametrize('boundary', [datetime.min, datetime.max])
def test_fixed_offset_datetime_boundaries(boundary: datetime, offset: timedelta) -> None:
    base = boundary.replace(tzinfo=timezone(offset))
    inward = timedelta(microseconds=1 if boundary == datetime.min else -1)
    duration = Duration.from_timedelta(inward)
    assert base + Duration() == base
    assert duration.add_to(base) == base + inward
    assert (base + duration) - duration == base
    with pytest.raises(OverflowError):
        _ = base - duration


@pytest.mark.parametrize(
    ('boundary', 'zone_name', 'days'),
    [(datetime.min, 'Europe/Berlin', 1), (datetime.max, 'America/New_York', -1)],
)
def test_zoneinfo_boundary_can_advance_into_representable_utc(
    boundary: datetime, zone_name: str, days: int
) -> None:
    base = boundary.replace(tzinfo=ZoneInfo(zone_name))
    assert base + Duration() == base
    result = base + Duration(days=days)
    assert result == base + timedelta(days=days)


def test_zero_duration_preserves_fold() -> None:
    base = datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=ZoneInfo('America/New_York'))
    result = base + Duration()
    assert result.fold == 1
    assert result.timestamp() == base.timestamp()


def test_from_timedelta_preserves_duration_subclass() -> None:
    class SpecializedDuration(Duration):
        pass

    result = SpecializedDuration.from_timedelta(timedelta(microseconds=-1))
    assert type(result) is SpecializedDuration
    assert result.nanoseconds == -1_000


def test_constructor_accepts_integer_subclasses() -> None:
    class Count(int):
        pass

    assert Duration(seconds=Count(2)) == Duration(seconds=2)


@given(st.integers(), st.integers())
def test_arithmetic_against_integer_nanoseconds(left: int, right: int) -> None:
    first = Duration(nanoseconds=left)
    second = Duration(nanoseconds=right)
    assert (first + second).nanoseconds == left + right
    assert (first - second).nanoseconds == left - right
    assert (first * right).nanoseconds == left * right
    assert (right * first).nanoseconds == right * left


@given(st.integers(), st.timedeltas())
def test_mixed_arithmetic_preserves_precision(nanoseconds: int, delta: timedelta) -> None:
    value = Duration(nanoseconds=nanoseconds)
    expected = (delta.days * 86_400 + delta.seconds) * 10**9 + delta.microseconds * 1_000
    assert (value + delta).nanoseconds == nanoseconds + expected
    assert (delta + value).nanoseconds == nanoseconds + expected
    assert (value - delta).nanoseconds == nanoseconds - expected
    assert (delta - value).nanoseconds == expected - nanoseconds


@given(
    st.datetimes(
        min_value=datetime(1900, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=st.sampled_from(
            [
                ZoneInfo('America/New_York'),
                ZoneInfo('Australia/Lord_Howe'),
                ZoneInfo('Pacific/Apia'),
                ZoneInfo('Europe/Berlin'),
                UTC,
            ]
        ),
    ),
    st.timedeltas(min_value=timedelta(days=-600), max_value=timedelta(days=600)),
)
def test_aware_arithmetic_against_utc(base: datetime, delta: timedelta) -> None:
    result = base + Duration.from_timedelta(delta)
    expected = base.astimezone(UTC) + delta
    assert result.astimezone(UTC) == expected
    assert result.tzinfo is base.tzinfo
