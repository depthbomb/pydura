# pydura

Parse, format, and apply human-readable durations with nanosecond precision.

```python
from pydura import Duration, format_duration, parse

delay = parse('1 day, 3h & 15m')

str(delay)  # '1 day 3 hours 15 minutes'
format_duration(delay, max_units=2)  # '1 day 3 hours'
delay.total_seconds()  # 98100.0
```

## Getting started

With a Python 3.14+ virtual environment active:

```console
python -m pip install pydura
```

There are three things to get familiar with:

- `parse(text)` reads a duration from text.
- `Duration(...)` builds one from integer amounts, like `Duration(minutes=5)`.
- `format_duration(value)` writes a duration or `timedelta` as words.

## Reading durations

Compact strings, full words, and a bit of extra text all work:

```python
parse('1h30m')
parse('1.5 hours')
parse('wait 1 hour and another 30 minutes')
# All three give you the same duration.
```

Units are case-insensitive, and whitespace between a number and its unit is fine.
Here are the supported spellings:

| Unit | Spellings |
| --- | --- |
| Year | `y`, `yr`, `yrs`, `year`, `years` |
| Month | `mo`, `mon`, `mons`, `month`, `months` |
| Week | `w`, `wk`, `wks`, `week`, `weeks` |
| Day | `d`, `day`, `days` |
| Hour | `h`, `hr`, `hrs`, `hour`, `hours` |
| Minute | `m`, `min`, `mins`, `minute`, `minutes` |
| Second | `s`, `sec`, `secs`, `second`, `seconds` |
| Millisecond | `ms`, `msec`, `msecs`, `millisecond`, `milliseconds` |
| Microsecond | `us`, `µs`, `μs`, `usec`, `microsecond`, `microseconds` |
| Nanosecond | `ns`, `nsec`, `nanosecond`, `nanoseconds` |

A year is always **365 days**, a month **30 days**, a week **7 days**, and a day
**24 hours**. These are elapsed durations, so adding a month won't adjust for
which calendar month you're in.

### Extra text and errors

The parser picks out the number-and-unit pairs it knows and skips everything
else. `1h 999 elephants` gives you one hour. If nothing matches, it raises
`ValueError`. Non-string input raises `TypeError`.

That makes it forgiving, but also means it won't catch every typo. A bare `0`
needs a unit (`0s` works), and scientific notation, `HH:MM` times, and ISO 8601
durations aren't supported. For example, `1e3s` becomes three seconds because
`1e` is skipped. Keep that in mind if you're validating user input.

### Negative durations

A sign on the first recognized component becomes the default for later unsigned
components. A later explicit sign affects just that component:

```python
str(parse('-1h30m'))  # '-1 hour 30 minutes'
str(parse('-1h+30m15m'))  # '-45 minutes': -60 + 30 - 15
str(parse('1h-30m15m'))  # '45 minutes': 60 - 30 + 15
```

## Working with a duration

Build a duration with any mix of integer `weeks`, `days`, `hours`, `minutes`,
`seconds`, `milliseconds`, `microseconds`, and `nanoseconds`:

```python
timeout = Duration(seconds=30, milliseconds=500)

timeout * 2  # Duration(nanoseconds=61000000000)
timeout + Duration(seconds=5)  # Duration(nanoseconds=35500000000)
timeout - Duration(milliseconds=500)  # Duration(nanoseconds=30000000000)
```

Values are immutable, so arithmetic gives you a new duration. You can add and
subtract durations or `timedelta` objects, multiply by an integer in either
order, negate a duration, or take its `abs()`.

Durations can also be sorted, compared with each other, and used as dictionary
keys. Only a zero duration is false in a boolean check. To compare with a
`timedelta`, convert it with `Duration.from_timedelta()` first.

The constructor accepts integers, including negative ones. Use `parse('1.5h')`
for fractions; passing a float or boolean to the constructor raises `TypeError`.

### Precision

Every duration stores an exact integer `.nanoseconds` value:

```python
parse('1.000000001s').nanoseconds  # 1000000001
```

Parsing uses exact decimal arithmetic. Each component drops any fraction of a
nanosecond toward zero before the components are added, so `0.5ns 0.5ns` is zero.
Use `.total_seconds()` when you want a float and don't need every nanosecond.

Values can grow beyond a signed 64-bit integer. Python's integer-string digit
limit still applies to exceptionally long whole-number inputs and formatted output.

## Dates and timedeltas

Add a duration to a `datetime`, or convert it to and from a `timedelta`:

```python
from datetime import UTC, datetime, timedelta

delay = parse('1h30m')
start = datetime(2026, 1, 1, 12, tzinfo=UTC)

start + delay  # 2026-01-01 13:30:00+00:00
start - delay  # 2026-01-01 10:30:00+00:00
delay.to_timedelta()  # timedelta(seconds=5400)
Duration.from_timedelta(timedelta(minutes=90)) == delay  # True
```

Timezone-aware datetimes keep their timezone. Adding `1d` advances exactly 24
elapsed hours, including across daylight saving changes, so the local clock
hour may change. Naive datetimes stay naive.

Python's `timedelta` stores microseconds. If conversion would lose nanoseconds,
pydura raises `ValueError` unless you explicitly allow truncation:

```python
parse('1501ns').to_timedelta(truncate=True)  # timedelta(microseconds=1)
parse('-1501ns').to_timedelta(truncate=True)  # timedelta(microseconds=-1)
parse('1501ns').add_to(start, truncate=True)
```

Datetime arithmetic uses exact conversion by default. Use `add_to()` with
`truncate=True` when dropping the remainder is okay.

Conversions and datetime arithmetic can raise `OverflowError` outside the
standard library's supported range. Timezones with changing offsets also need
the resulting UTC datetime to fit that range.

## Turning durations into words

`str(duration)` includes every nonzero component, down to nanoseconds.
`format_duration()` does the same and also accepts a `timedelta`:

```python
format_duration(timedelta(hours=2, minutes=15))  # '2 hours 15 minutes'
format_duration(parse('2h15m3s'), max_units=2)  # '2 hours 15 minutes'
str(Duration())  # '0 milliseconds'
```

`max_units` limits the number of nonzero components. Smaller units are left off
without rounding. Use a positive integer, or `None` for everything. Full output
can be passed back to `parse()` without losing precision.

## Development

With the project's virtual environment active:

```console
python -m pip install -e ".[dev]"
python -m pytest --cov=pydura --cov-branch
python -m ruff check .
python -m mypy
python -m build
python -m twine check --strict dist/*
python benchmarks/benchmark.py
```

Ruff handles linting only. Code formatting is maintained manually.

The benchmark runner covers parsing, formatting, arithmetic, and large inputs.
Pass `--baseline /path/to/saved_duration.py` to compare with a saved copy of
`pydura/_duration.py`. Add `--json /path/to/results.json` to keep the measurements.
