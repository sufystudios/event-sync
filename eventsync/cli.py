"""eventsync: line up recordings by what happens in them. Every command prints one JSON object."""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from . import core
from .core import Roi


def _roi(text):
    return Roi.parse(text) if text else None


def cmd_onset(o):
    t = core.audio_onset(o.file, after=o.after, threshold_db=o.threshold_db)
    return {'file': o.file, 'onset': round(t, 4)}


def cmd_event(o):
    t = core.color_event(o.file, Roi.parse(o.roi), o.color, o.min_fraction, o.after, o.fps, o.change)
    return {'file': o.file, 'event': round(t, 4), 'roi': o.roi, 'color': None if o.change else o.color}


def cmd_offset(o):
    """A visual event in A (a key lighting up) and the sound starting in B."""
    a = core.color_event(o.a, Roi.parse(o.a_roi), o.a_color, o.min_fraction, o.a_after, o.fps, o.a_change)
    b = core.audio_onset(o.b, after=o.b_after, threshold_db=o.threshold_db)
    return {
        'a': o.a, 'b': o.b, 'a_event': round(a, 4), 'b_event': round(b, 4),
        'shift': round(b - a, 4),
        'meaning': 'time t in A shows what is heard at t + shift in B',
        'trim': {'a_start': round(max(0.0, a - o.pre), 4), 'b_start': round(max(0.0, b - o.pre), 4)},
    }


def _series_of(path, kind, roi, fps, color):
    return core.series(path, kind, _roi(roi), fps, color)


def cmd_align(o):
    a = _series_of(o.a, o.a_series, o.a_roi, o.fps, o.a_color)
    b = _series_of(o.b, o.b_series, o.b_roi, o.fps, o.b_color)
    metric = o.metric or ('mae' if o.a_series == o.b_series == 'knob' else 'corr')
    lag, score = core.best_lag(a, b, int(o.max_lag * o.fps), metric)
    return {
        'a': o.a, 'b': o.b, 'shift': round(lag / o.fps, 4), 'metric': metric, 'score': round(score, 4),
        'frames_compared': int(min(len(a), len(b))),
        'meaning': 'time t in A matches time t + shift in B',
    }


def cmd_verify(o):
    """Two views inside one finished file should already line up: report how far apart they are."""
    r = cmd_align(argparse.Namespace(a=o.file, b=o.file, a_series=o.a_series, b_series=o.b_series,
                                     a_roi=o.a_roi, b_roi=o.b_roi, a_color=o.color, b_color=o.color,
                                     fps=o.fps, max_lag=o.max_lag, metric=o.metric))
    ms = r['shift'] * 1000
    r.update({'offset_ms': round(ms, 1), 'tolerance_ms': o.tolerance_ms, 'ok': abs(ms) <= o.tolerance_ms})
    return r


def cmd_series(o):
    s = _series_of(o.file, o.kind, o.roi, o.fps, o.color)
    if o.out.endswith('.npy'):
        np.save(o.out, s)
    else:
        np.savetxt(o.out, np.column_stack([np.arange(len(s)) / o.fps, s]), delimiter=',', header='time,value',
                   comments='', fmt='%.4f')
    return {'file': o.file, 'kind': o.kind, 'frames': int(len(s)), 'fps': o.fps, 'out': o.out,
            'min': float(s.min()), 'max': float(s.max())}


def build_parser():
    p = argparse.ArgumentParser(prog='eventsync', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('onset', help='when the sound starts')
    s.add_argument('file'); s.add_argument('--after', type=float, default=0.0)
    s.add_argument('--threshold-db', type=float, default=-45.0)
    s.set_defaults(fn=cmd_onset)

    s = sub.add_parser('event', help='when a screen region turns a color (or changes)')
    s.add_argument('file'); s.add_argument('--roi', required=True, help='x,y,w,h in video pixels')
    s.add_argument('--color', default='green', help=f'{", ".join(sorted(core.COLORS))} or rgb:R,G,B[,tol]')
    s.add_argument('--min-fraction', type=float, default=0.25); s.add_argument('--after', type=float, default=0.0)
    s.add_argument('--change', action='store_true', help='any visible change instead of a color')
    s.add_argument('--fps', type=float, default=30.0)
    s.set_defaults(fn=cmd_event)

    s = sub.add_parser('offset', help='a visual event in A against the sound starting in B')
    s.add_argument('--a', required=True, help='the screen recording'); s.add_argument('--a-roi', required=True)
    s.add_argument('--a-color', default='green'); s.add_argument('--a-after', type=float, default=0.0)
    s.add_argument('--a-change', action='store_true')
    s.add_argument('--b', required=True, help='the recording whose audio you will use')
    s.add_argument('--b-after', type=float, default=0.0, help='ignore sound before this (e.g. a count-in)')
    s.add_argument('--threshold-db', type=float, default=-45.0)
    s.add_argument('--min-fraction', type=float, default=0.25); s.add_argument('--pre', type=float, default=0.5,
                                                                              help='seconds to keep before the event')
    s.add_argument('--fps', type=float, default=30.0)
    s.set_defaults(fn=cmd_offset)

    for name, fn, helptext in (('align', cmd_align, 'the shift that best matches two series (two files)'),):
        s = sub.add_parser(name, help=helptext)
        s.add_argument('--a', required=True); s.add_argument('--b', required=True)
        s.add_argument('--a-series', required=True, choices=sorted(core.SERIES))
        s.add_argument('--b-series', required=True, choices=sorted(core.SERIES))
        s.add_argument('--a-roi'); s.add_argument('--b-roi')
        s.add_argument('--a-color'); s.add_argument('--b-color')
        s.add_argument('--metric', choices=['corr', 'mae'])
        s.add_argument('--max-lag', type=float, default=3.0, help='seconds to search either way')
        s.add_argument('--fps', type=float, default=30.0)
        s.set_defaults(fn=fn)

    s = sub.add_parser('verify', help='check two views inside one finished video line up')
    s.add_argument('file')
    s.add_argument('--a-series', required=True, choices=sorted(core.SERIES)); s.add_argument('--a-roi')
    s.add_argument('--b-series', required=True, choices=sorted(core.SERIES)); s.add_argument('--b-roi')
    s.add_argument('--color'); s.add_argument('--metric', choices=['corr', 'mae'])
    s.add_argument('--max-lag', type=float, default=1.0); s.add_argument('--fps', type=float, default=30.0)
    s.add_argument('--tolerance-ms', type=float, default=40.0)
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser('series', help='write one series to .csv or .npy, to plot or inspect')
    s.add_argument('file'); s.add_argument('--kind', required=True, choices=sorted(core.SERIES))
    s.add_argument('--roi'); s.add_argument('--color'); s.add_argument('--fps', type=float, default=30.0)
    s.add_argument('--out', required=True)
    s.set_defaults(fn=cmd_series)
    return p


def main(argv=None):
    o = build_parser().parse_args(argv)
    try:
        result = o.fn(o)
    except core.EventNotFound as e:
        print(json.dumps({'error': 'not_found', 'message': str(e)}))
        return 2
    except (ValueError, RuntimeError) as e:
        print(json.dumps({'error': 'bad_input', 'message': str(e)}))
        return 1
    print(json.dumps(result, indent=2))
    if o.cmd == 'verify' and not result['ok']:
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
