from re import compile
from dataclasses import dataclass
from types import NotImplementedType
from typing import Optional, overload
from datetime import UTC, datetime, timedelta, timezone

_COMPONENT = compile(r'([+\-0-9][0-9]*(?:\.[0-9]*)?|\.[0-9]+)\s*([a-zA-Z]*)')
_UNITS = (
    ('year', 31_536_000_000_000_000, 'y yr yrs year years'),
    ('month', 2_592_000_000_000_000, 'mo mon mons month months'),
    ('week', 604_800_000_000_000, 'w wk wks week weeks'),
    ('day', 86_400_000_000_000, 'd day days'),
    ('hour', 3_600_000_000_000, 'h hr hrs hour hours'),
    ('minute', 60_000_000_000, 'm min mins minute minutes'),
    ('second', 1_000_000_000, 's sec secs second seconds'),
    ('millisecond', 1_000_000, 'ms msec msecs millisecond milliseconds'),
    ('microsecond', 1_000, 'us µs μs usec microsecond microseconds'),
    ('nanosecond', 1, 'ns nsec nanosecond nanoseconds'),
)
_MULTIPLIERS = {alias: multiplier for _, multiplier, aliases in _UNITS for alias in aliases.split()}
_MULTIPLIERS.update({'µſ': 1_000, 'μſ': 1_000})
_FORMAT_UNITS = tuple((name, name + 's', multiplier) for name, multiplier, _ in _UNITS)
_DECIMAL_SCALES: tuple[int, ...] = tuple(10**exponent for exponent in range(65))
_CONSTRUCTOR_UNITS = (
    'weeks',
    'days',
    'hours',
    'minutes',
    'seconds',
    'milliseconds',
    'microseconds',
    'nanoseconds',
)


@dataclass(frozen=True, slots=True, init=False, order=True)
class Duration:
    """
    An immutable elapsed duration stored as integer nanoseconds.

    Constructor units must be integers; use :func:`parse` for decimal text.
    Weeks are seven days. Values are not restricted to Go's signed 64-bit range.
    Ordering and equality compare Duration instances, not other numeric types.
    """

    nanoseconds: int

    def __init__(
        self,
        *,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        milliseconds: int = 0,
        microseconds: int = 0,
        nanoseconds: int = 0,
    ) -> None:
        amounts = (weeks, days, hours, minutes, seconds, milliseconds, microseconds, nanoseconds)
        if not all(type(amount) is int for amount in amounts):
            for name, amount in zip(_CONSTRUCTOR_UNITS, amounts, strict=True):
                _require_int(amount, name)

        total_hours = (weeks * 7 + days) * 24 + hours
        total_seconds = (total_hours * 60 + minutes) * 60 + seconds
        total = (
            (total_seconds * 1_000 + milliseconds) * 1_000 + microseconds
        ) * 1_000 + nanoseconds

        object.__setattr__(self, 'nanoseconds', total)

    def __str__(self) -> str:
        return format_duration(self)

    def __bool__(self) -> bool:
        return self.nanoseconds != 0

    def __neg__(self) -> Duration:
        return _from_nanoseconds(-self.nanoseconds)

    def __pos__(self) -> Duration:
        return self

    def __abs__(self) -> Duration:
        return _from_nanoseconds(abs(self.nanoseconds))

    @overload
    def __add__(self, other: Duration | timedelta) -> Duration: ...

    @overload
    def __add__(self, other: datetime) -> datetime: ...

    def __add__(self, other: object) -> Duration | datetime | NotImplementedType:
        if isinstance(other, datetime):
            return self.add_to(other)

        if isinstance(other, timedelta):
            return _from_nanoseconds(self.nanoseconds + _timedelta_nanoseconds(other))

        if isinstance(other, Duration):
            return _from_nanoseconds(self.nanoseconds + other.nanoseconds)

        return NotImplemented

    @overload
    def __radd__(self, other: Duration | timedelta) -> Duration: ...

    @overload
    def __radd__(self, other: datetime) -> datetime: ...

    def __radd__(self, other: object) -> Duration | datetime | NotImplementedType:
        if isinstance(other, (Duration, timedelta, datetime)):
            return self + other

        return NotImplemented

    def __sub__(self, other: Duration | timedelta) -> Duration:
        if isinstance(other, timedelta):
            return _from_nanoseconds(self.nanoseconds - _timedelta_nanoseconds(other))

        if isinstance(other, Duration):
            return _from_nanoseconds(self.nanoseconds - other.nanoseconds)

        return NotImplemented

    @overload
    def __rsub__(self, other: Duration | timedelta) -> Duration: ...

    @overload
    def __rsub__(self, other: datetime) -> datetime: ...

    def __rsub__(self, other: object) -> Duration | datetime | NotImplementedType:
        if isinstance(other, datetime):
            return (-self).add_to(other)

        if isinstance(other, timedelta):
            return _from_nanoseconds(_timedelta_nanoseconds(other) - self.nanoseconds)

        if isinstance(other, Duration):
            return _from_nanoseconds(other.nanoseconds - self.nanoseconds)

        return NotImplemented

    def __mul__(self, factor: int) -> Duration:
        if not isinstance(factor, int) or isinstance(factor, bool):
            return NotImplemented

        return _from_nanoseconds(self.nanoseconds * factor)

    def __rmul__(self, factor: int) -> Duration:
        return self.__mul__(factor)

    def total_seconds(self) -> float:
        """Return floating-point seconds, which may lose nanosecond precision."""
        return self.nanoseconds / 1_000_000_000

    def to_timedelta(self, *, truncate: bool = False) -> timedelta:
        """
        Convert to timedelta, rejecting sub-microsecond loss by default.

        With truncate=True, discard sub-microseconds toward zero. Python raises
        OverflowError when the result is outside timedelta's supported range.
        """
        if not isinstance(truncate, bool):
            raise TypeError('truncate must be a bool')

        magnitude, remainder = divmod(abs(self.nanoseconds), 1_000)
        if remainder and not truncate:
            raise ValueError(
                'duration has sub-microsecond precision; use truncate=True to discard it'
            )

        microseconds = -magnitude if self.nanoseconds < 0 else magnitude

        return timedelta(microseconds=microseconds)

    def add_to(self, base: datetime, *, truncate: bool = False) -> datetime:
        """
        Add elapsed time, using UTC for timezone-aware datetime values.

        This preserves elapsed-time semantics across daylight saving changes.
        The result uses base's timezone. Naive datetimes remain naive.
        Sub-microsecond loss requires truncate=True, as with to_timedelta().
        """
        if not isinstance(base, datetime):
            raise TypeError('base must be a datetime')

        delta = self.to_timedelta(truncate=truncate)
        if not delta:
            return base

        if isinstance(base.tzinfo, timezone):
            return base + delta

        offset = base.utcoffset()
        if offset is not None:
            # Combine the adjustment before applying it, so conversion of the
            # starting instant cannot overflow when the result is representable.
            utc_result = base.replace(tzinfo=UTC) + (delta - offset)

            return utc_result.astimezone(base.tzinfo)

        return base + delta

    @classmethod
    def from_timedelta(cls, value: timedelta) -> Duration:
        """Create a duration without passing through floating-point seconds."""
        if not isinstance(value, timedelta):
            raise TypeError('value must be a timedelta')

        nanoseconds = _timedelta_nanoseconds(value)
        if cls is Duration:
            return _from_nanoseconds(nanoseconds)

        return cls(nanoseconds=nanoseconds)


def _from_nanoseconds(value: int) -> Duration:
    """Build an internal result whose integer value is already validated."""
    result = object.__new__(Duration)
    object.__setattr__(result, 'nanoseconds', value)

    return result


def _timedelta_nanoseconds(value: timedelta) -> int:
    return ((value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds) * 1_000


def _require_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f'{name} must be an int')


def _fraction_nanoseconds(fraction: str, multiplier: int) -> int:
    if len(fraction) <= 64:
        return int(fraction) * multiplier // _DECIMAL_SCALES[len(fraction)]

    # Process decimal blocks right to left. Each division discards only digits
    # that cannot affect the eventual whole-nanosecond result.
    result = 0
    for end in range(len(fraction), 0, -18):
        start = max(0, end - 18)
        result = (result + int(fraction[start:end]) * multiplier) // _DECIMAL_SCALES[end - start]

    return result


def parse(text: str) -> Duration:
    """
    Extract and sum duration components from text, ignoring unknown words.

    Units are case-insensitive. A year is 365 days, a month 30 days, and a week
    seven days. Decimal components truncate separately toward whole nanoseconds.
    A sign on the first recognized component sets the default for unsigned
    components; later explicit signs affect only their own component.

    Raise ValueError if no duration is found. Python's integer-string conversion
    limit applies to exceptionally long whole-number components.
    """
    if not isinstance(text, str):
        raise TypeError('text must be a str')

    total = 0
    default_sign = 1
    found = False
    position = 0
    while match := _COMPONENT.search(text, position):
        position = match.end()
        number, unit = match.groups()
        while position < len(text) and text[position].isalpha():
            position += 1

        if position != match.end():
            unit = text[match.start(2) : position]

        multiplier = _MULTIPLIERS.get(unit.lower())
        if multiplier is None:
            continue

        sign = default_sign
        if number[0] in '+-':
            sign = -1 if number[0] == '-' else 1
            number = number[1:]
            if not number or number == '.':
                continue

        if not found:
            default_sign = sign

        whole, _, fraction = number.partition('.')
        amount = int(whole.lstrip('0') or '0') * multiplier
        if fraction:
            amount += _fraction_nanoseconds(fraction, multiplier)

        total += sign * amount
        found = True

    if not found:
        raise ValueError('no duration found')

    return _from_nanoseconds(total)


def format_duration(value: Duration | timedelta, *, max_units: Optional[int] = None) -> str:
    """
    Render a duration as words, optionally limiting nonzero components.

    max_units must be a positive integer or None for all components. A limit
    discards smaller components without rounding. Zero is '0 milliseconds'.
    """
    if max_units is not None:
        _require_int(max_units, 'max_units')
        if max_units <= 0:
            raise ValueError('max_units must be positive')

    if isinstance(value, timedelta):
        nanoseconds = _timedelta_nanoseconds(value)
    elif isinstance(value, Duration):
        nanoseconds = value.nanoseconds
    else:
        raise TypeError('value must be a Duration or timedelta')

    remaining = abs(nanoseconds)
    if not remaining:
        return '0 milliseconds'

    parts = []
    for singular, plural, multiplier in _FORMAT_UNITS:
        if remaining < multiplier:
            continue

        amount, remaining = divmod(remaining, multiplier)
        parts.append(f'{amount} {singular if amount == 1 else plural}')
        if not remaining or (max_units is not None and len(parts) == max_units):
            break

    sign = '-' if nanoseconds < 0 else ''

    return sign + ' '.join(parts)
