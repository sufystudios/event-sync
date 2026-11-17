# event-sync

Line up a screen recording and a separately recorded sound **by what happens in them** (a key lighting up, a sound starting, a knob turning) instead of by their clocks.

You record an app's screen on one device and its sound somewhere else: a phone playing a desktop plugin over Wi-Fi, a game streamed to a PC, a MIDI controller and a DAW. The two never start at the same moment, and the sound arrives late by an amount that changes from take to take (0.84–1.14 s over Wi-Fi in the case this was built for). Put them side by side by timestamps and viewers see the UI running ahead of the sound. `eventsync` finds the shift from the content itself and checks the finished video.

```
$ eventsync offset --a phone.mp4 --a-roi 740,600,80,80 --b plugin.mov
{ "a_event": 6.5, "b_event": 7.435, "shift": 0.935,
  "trim": { "a_start": 6.0, "b_start": 6.935 }, ... }

$ eventsync verify final.mp4 --a-series knob --a-roi 290,347,106,106 --b-series brightness
{ "offset_ms": 0.0, "ok": true, "score": 0.97, ... }
```

Built for, and tested on, the promo videos of [DroneSynth](https://play.google.com/store/apps/details?id=xyz.sufystudios.synthguide), where an Android phone plays the free DroneSynth desktop plugin.

## What it can measure

| Command | Finds |
|---|---|
| `onset FILE` | when the sound starts (first window above -45 dBFS) |
| `event FILE --roi x,y,w,h --color green` | when part of the screen turns a color (a key, a button, an LED), or `--change` for any visible change |
| `offset --a SCREEN --a-roi .. --b AUDIOFILE` | both of those, and the shift between them, plus where to trim each file |
| `align --a .. --a-series S --b .. --b-series S` | the shift that best matches two signals: `knob` (a rotary knob's angle), `motion` (how much a region changes), `envelope` (loudness), `brightness` (spectral centroid: follows filter sweeps) |
| `verify FINAL --a-series .. --b-series ..` | how far apart two views inside one finished video are; exits 3 if over `--tolerance-ms` |
| `series FILE --kind .. --out x.csv` | one signal over time, to plot or check |

Every command prints one JSON object. Exit codes: 0 ok, 1 bad input, 2 event not found, 3 verify out of tolerance.

## Install

Needs Python 3.9+, numpy and [ffmpeg](https://ffmpeg.org) on PATH.

```
pip install git+https://github.com/sufystudios/event-sync
# or, from a clone:
pip install -e .        # then: eventsync --help
python3 -m eventsync --help   # without installing
```

## Typical recipe

1. Record the take: screen (phone, simulator, window) and the sound source (plugin window with app audio, a DAW, a mic). Note roughly when the key is pressed.
2. Find a region that changes when the action happens. Grab a frame (`ffmpeg -ss 5 -i phone.mp4 -frames:v 1 f.png`) and read the pixel box of the key or button.
3. `eventsync offset --a phone.mp4 --a-roi .. --b plugin.mov` and cut each file from its `trim` value. The two now start together.
4. When a knob or slider moves on both screens, `align` with `knob` or `motion` on both gives a more exact shift than a single event, and `brightness` checks the sound follows the knob.
5. After composing: `eventsync verify final.mp4 ...` on two regions (or a region and the audio) of the finished video. Ship only when `ok` is true.

See [AGENTS.md](AGENTS.md) for the details an AI agent needs, and `examples/` for a runnable demo.

## Tests

```
python3 -m unittest discover -s tests -v
```

The tests make their own recordings (`tests/synth.py`): a button that lights at 2.00 s, a knob sweep, and the same knob and a matching sound 0.90 s later. Every command must recover those numbers.

## License

MIT. See [LICENSE](LICENSE).
