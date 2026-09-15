import pytest
from fractions import Fraction
from hypothesis import given, settings
from hypothesis import strategies as st
from pydura import Duration, parse, format_duration

@pytest.mark.parametrize(
        ('text', 'nanoseconds'),
        [
            ('1d3h15m3s', 98_103_000_000_000),
            ('1 day, 3h & 15m, plus another 3 seconds', 98_103_000_000_000),
            ('1.5 hours and 250 ms', 5_400_250_000_000),
            ('1y2mo3w', (365 + 60 + 21) * 86_400_000_000_000),
            ('-1d3h', -27 * 3_600_000_000_000),
            ('-1d-3h', -27 * 3_600_000_000_000),
            ('-1d+3h', -21 * 3_600_000_000_000),
            ('1d-3h', 21 * 3_600_000_000_000),
            ('1d+3h', 27 * 3_600_000_000_000),
            ('-1h+30m15m', -45 * 60_000_000_000),
            ('1h-30m15m', 45 * 60_000_000_000),
            ('-0s1s', -1_000_000_000),
            ('999 elephants 1h', 3_600_000_000_000),
            ('1elephants2h', 7_200_000_000_000),
            ('-1elephants2h', 7_200_000_000_000),
            ('1elephants-2h3m', -7_380_000_000_000),
            ('1 \t\n\r\v\f -2h', -7_200_000_000_000),
            ('1\u2003\u00a0elephants+2h', 7_200_000_000_000),
            ('1未知2h', 7_200_000_000_000),
            ('文字🙂1µs', 1_000),
            ('4µſ', 4_000),
            ('4μſ', 4_000),
            ('4Μſ', 4_000),
            ('1 2h', 7_200_000_000_000),
            ('1..5h', 1_800_000_000_000),
            ('1e3s', 3_000_000_000),
            ('1.s', 1_000_000_000),
            ('+h -2s', -2_000_000_000),
            ('---1s', -1_000_000_000),
            ('-.h1s', 1_000_000_000),
            ('+..5s', 500_000_000),
            ('+.h -2s3s', -5_000_000_000),
            ('- h 2s', 2_000_000_000),
            ('0.5ns 0.5ns', 0),
            ('-1.9ns +.5ns', -1),
            ('9223372036.854775807s', 2 ** 63 - 1),
            ('-9223372036.854775808s', -(2 ** 63)),
            ('9223372036854775807ns 1ns -1ns', 2 ** 63 - 1),
            ('-9223372036854775808ns -1ns +1ns', -(2 ** 63)),
            ('300y -300y .5us -.5ns .5ns', 500),
            ('-300y +300y 1ns', -1),
            ('0.' + '0' * 10 + '3' * 30 + 'm', 1),
            ('0.' + '0' * 10 + '5' + '0' * 30 + 'm', 3),
            ('0.' + '9' * 40 + 'y', 31_536_000_000_000_000 - 1),
            ('0.5' + '0' * 5_000 + 'y', 31_536_000_000_000_000 // 2),
            ('0' * 5_000 + '1ns', 1),
            ('9' * 100 + 'y -' + '9' * 100 + 'y 1ns', 1),
            ('-' + '9' * 100 + 'y +' + '9' * 100 + 'y 1ns', -1),
        ],
)
def test_parser_regressions(text: str, nanoseconds: int) -> None:
    assert parse(text).nanoseconds == nanoseconds

@pytest.mark.parametrize(
        ('aliases', 'nanoseconds'),
        [
            ('y yr yrs year years', 365 * 86_400 * 10 ** 9),
            ('mo mon mons month months', 30 * 86_400 * 10 ** 9),
            ('w wk wks week weeks', 7 * 86_400 * 10 ** 9),
            ('d day days', 86_400 * 10 ** 9),
            ('h hr hrs hour hours', 3_600 * 10 ** 9),
            ('m min mins minute minutes', 60 * 10 ** 9),
            ('s sec secs second seconds', 10 ** 9),
            ('ms msec msecs millisecond milliseconds', 10 ** 6),
            ('us µs μs usec microsecond microseconds', 10 ** 3),
            ('ns nsec nanosecond nanoseconds', 1),
        ],
)
def test_aliases_and_case(aliases: str, nanoseconds: int) -> None:
    for alias in aliases.split():
        mixed = ''.join(c.upper() if i % 2 else c for i, c in enumerate(alias))
        for spelling in (alias, alias.upper(), mixed):
            assert parse('1' + spelling).nanoseconds == nanoseconds

@pytest.mark.parametrize(
        'text', ['', 'nothing', '1', '0', '1elephants', '1未知', '+-.', '文字🙂', '１h', '1hoursuffix']
)
def test_no_recognized_duration(text: str) -> None:
    with pytest.raises(ValueError, match='no duration found'):
        parse(text)

@pytest.mark.parametrize('value', [None, 1, 1.5, b'1h', Duration(hours=1)])
def test_parse_rejects_non_text(value: object) -> None:
    with pytest.raises(TypeError, match='text must be a str'):
        parse(value)

def test_values_can_exceed_go_int64_range() -> None:
    assert parse('9223372036854775808ns').nanoseconds == 2 ** 63
    assert parse('-9223372036854775809ns').nanoseconds == -(2 ** 63) - 1
    assert parse('9' * 100 + 'ns').nanoseconds == 10 ** 100 - 1

@given(st.integers(min_value=-(10 ** 100), max_value=10 ** 100))
@settings(max_examples=500)
def test_format_parse_round_trip(nanoseconds: int) -> None:
    value = Duration(nanoseconds=nanoseconds)
    assert parse(str(value)) == value
    assert parse(format_duration(value)) == value

@given(
        whole=st.integers(min_value=0, max_value=10 ** 20),
        fraction=st.text(alphabet='0123456789', min_size=1, max_size=200),
        sign=st.sampled_from(['', '+', '-']),
        unit=st.sampled_from(
                [
                    ('y', 365 * 86_400 * 10 ** 9),
                    ('mo', 30 * 86_400 * 10 ** 9),
                    ('w', 7 * 86_400 * 10 ** 9),
                    ('d', 86_400 * 10 ** 9),
                    ('h', 3_600 * 10 ** 9),
                    ('m', 60 * 10 ** 9),
                    ('s', 10 ** 9),
                    ('ms', 10 ** 6),
                    ('us', 10 ** 3),
                    ('ns', 1),
                ]
        ),
)
@settings(max_examples=1_000)
def test_decimals_against_exact_rational_arithmetic(
        whole: int, fraction: str, sign: str, unit: tuple[str, int]
) -> None:
    text = f'{sign}{whole}.{fraction}'
    alias, multiplier = unit
    expected = int(Fraction(text) * multiplier)
    assert parse(text + alias).nanoseconds == expected

@given(st.text(max_size=1_000))
def test_arbitrary_text(text: str) -> None:
    try:
        result = parse(text)
    except ValueError:
        return

    assert parse(str(result)) == result

@pytest.mark.parametrize('text', ['+h', '-h', '+.h', '-.h', '.h'])
def test_sign_without_a_number_is_not_a_duration(text: str) -> None:
    with pytest.raises(ValueError, match='no duration found'):
        parse(text)

@pytest.mark.parametrize('size', [18, 19, 63, 64, 65, 72, 128, 1_000, 10_000])
def test_long_fraction_thresholds_remain_exact(size: int) -> None:
    assert parse('0.' + '9' * size + 'y').nanoseconds == 365 * 86_400 * 10 ** 9 - 1
    assert parse('-0.5' + '0' * size + 'y').nanoseconds == -(365 * 86_400 * 10 ** 9 // 2)
    assert parse('0.' + '0' * 10 + '3' * size + 'm').nanoseconds == 1
    assert parse('0.' + '0' * 10 + '3' * size + '4m').nanoseconds == 2

@pytest.mark.parametrize('text', ['1h未知', '1sµ', '1HOURSé', '1mΜ', '1secſ'])
def test_ascii_unit_prefix_cannot_match_part_of_unicode_word(text: str) -> None:
    with pytest.raises(ValueError, match='no duration found'):
        parse(text)

def test_large_unknown_number_is_skipped_before_integer_conversion() -> None:
    assert parse('9' * 10_000 + 'elephants -1ns').nanoseconds == -1

@given(
        whole=st.integers(min_value=0, max_value=100),
        digits=st.text(alphabet='0123456789', min_size=65, max_size=1_000),
        multiplier=st.sampled_from([1, 1_000, 1_000_000, 1_000_000_000, 60_000_000_000]),
)
@settings(max_examples=300)
def test_block_fraction_arithmetic_against_rationals(
        whole: int, digits: str, multiplier: int
) -> None:
    aliases = {1: 'ns', 1_000: 'us', 1_000_000: 'ms', 1_000_000_000: 's', 60_000_000_000: 'm'}
    number = f'{whole}.{digits}'
    assert parse(number + aliases[multiplier]).nanoseconds == int(Fraction(number) * multiplier)
