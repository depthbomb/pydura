"""Benchmark the installed package, optionally against a saved _duration.py."""

from json import dumps
from sys import modules
from pathlib import Path
from timeit import Timer
from pydura import _duration
from types import ModuleType
from functools import partial
from statistics import median
from argparse import ArgumentParser
from platform import python_version
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location

def _load_baseline(path: Path) -> ModuleType:
    spec = spec_from_file_location('_pydura_baseline', path)
    if spec is None or spec.loader is None:
        raise ValueError(f'cannot load baseline: {path}')

    baseline = module_from_spec(spec)
    modules[spec.name] = baseline
    spec.loader.exec_module(baseline)

    return baseline

def _ignore_invalid(parse: Callable, text: str) -> None:
    try:
        parse(text)
    except ValueError:
        pass

def _cases(implementation: ModuleType) -> dict[str, tuple[Callable, int]]:
    parse = implementation.parse
    duration = implementation.Duration
    format_duration = implementation.format_duration
    samples = {
        'parse short': '1h30m',
        'parse compact': '1y2mo3w4d5h6m7s8ms',
        'parse prose': '1 day, 3h & 15m, plus another 3 seconds',
        'parse unicode': '1\u2003µs 2μs 3ΜS',
        'parse fractional': '0.123456789012345678901234567890y',
        'parse cancellation': '9' * 100 + 'y -' + '9' * 100 + 'y 1ns',
    }
    cases = {name: (partial(parse, text), 10_000) for name, text in samples.items()}
    cases['parse long fraction'] = (partial(parse, '0.' + '3' * 10_000 + 'm'), 100)
    cases['parse unknown units'] = (partial(parse, '999 elephants, ' * 100 + '1h'), 200)
    cases['reject prose 1MiB'] = (partial(_ignore_invalid, parse, 'x' * 2 ** 20), 2)
    cases['reject unit 1MiB'] = (partial(_ignore_invalid, parse, '1' + 'X' * 2 ** 20), 2)
    full = parse(samples['parse compact'])
    short = duration(hours=1)
    delta = timedelta(hours=1)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    cases.update(
            {
                'construct nanoseconds': (partial(duration, nanoseconds=1), 20_000),
                'construct mixed units': (partial(duration, days=1, hours=3, seconds=5), 20_000),
                'format all units': (partial(format_duration, full), 10_000),
                'format short': (partial(format_duration, short), 20_000),
                'format timedelta': (partial(format_duration, delta), 20_000),
                'add durations': (lambda: short + short, 20_000),
                'add timedelta': (lambda: short + delta, 20_000),
                'multiply': (lambda: short * 3, 20_000),
                'from timedelta': (partial(duration.from_timedelta, delta), 20_000),
                'to timedelta': (short.to_timedelta, 20_000),
                'add UTC datetime': (partial(short.add_to, base), 20_000),
            }
    )

    return cases

def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
            '--baseline', type=Path, help='saved _duration.py to compare in this process'
    )
    parser.add_argument('--json', type=Path, help='write benchmark measurements to this file')
    parser.add_argument('--repeat', type=int, default=7)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error('--repeat must be positive')

    current = _cases(_duration)
    baseline = _cases(_load_baseline(args.baseline)) if args.baseline else None
    measurements = {}
    print(f'Python {python_version()}; median of {args.repeat} runs; times in us/call')
    if baseline:
        print(f'{"case":26s} {"before":>12s} {"after":>12s} {"less time":>12s}')

    for name, (operation, count) in current.items():
        candidate_timer = Timer(operation)
        baseline_timer = Timer(baseline[name][0]) if baseline else None
        candidate_times = []
        baseline_times = []
        operation()
        for run in range(args.repeat):
            # Alternate order to reduce bias from CPU warm-up and background work.
            if baseline_timer and run % 2 == 0:
                baseline_times.append(baseline_timer.timeit(count) / count * 1_000_000)
            candidate_times.append(candidate_timer.timeit(count) / count * 1_000_000)
            if baseline_timer and run % 2:
                baseline_times.append(baseline_timer.timeit(count) / count * 1_000_000)

        after = median(candidate_times)
        result = {'after_us': after, 'after_samples_us': candidate_times}
        if baseline_times:
            before = median(baseline_times)
            saved = (1 - after / before) * 100
            result.update(
                    {
                        'before_us': before,
                        'before_samples_us': baseline_times,
                        'less_time_percent': saved,
                    }
            )
            print(f'{name:26s} {before:12.3f} {after:12.3f} {saved:11.1f}%')
        else:
            print(f'{name:26s} {after:12.3f}')

        measurements[name] = result

    if args.json:
        args.json.write_text(
                dumps(
                        {'python': python_version(), 'repeat': args.repeat, 'cases': measurements}, indent=2
                )
                + '\n',
                encoding='utf-8',
        )

if __name__ == '__main__':
    main()
