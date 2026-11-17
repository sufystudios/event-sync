"""event-sync: line up a screen recording and a separately recorded sound by events, not clocks."""
from .core import (EventNotFound, Roi, audio_onset, best_lag, brightness_series, color_event, envelope_series,
                   knob_series, motion_series, series)

__version__ = '0.1.0'
