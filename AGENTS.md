# AGENTS.md — event-sync

Instructions for AI coding agents using or changing this tool.

## When to use it

Use `eventsync` whenever a video combines **pictures from one recording and sound (or a second picture) from another**, and the two must look simultaneous: an app's screen next to the plugin/desktop/console it controls, a phone screen with audio recorded on a computer, two screens of the same performance. Don't line such recordings up by file timestamps or "it started about 1 s later": network and audio-buffer latency varies per take. Measure each take.

## Contract

- Run: `eventsync <command> ...` (installed) or `python3 -m eventsync <command> ...` from the repo root.
- Output: exactly one JSON object on stdout. Parse it; don't scrape text.
- Exit codes: `0` ok · `1` bad input (`{"error": "bad_input"}`) · `2` event not found (`{"error": "not_found"}`) · `3` `verify` out of tolerance (JSON still printed, `"ok": false`).
- Times are seconds from the start of each file. `shift` always means: **time t in A matches time t + shift in B.**
- ROIs are `x,y,w,h` in the file's own pixels (not points, not the size of a preview).

## Commands

| Command | Use it for | Key output |
|---|---|---|
| `onset FILE [--after S] [--threshold-db -45]` | first moment of sound | `onset` |
| `event FILE --roi R [--color green\|red\|blue\|yellow\|white\|bright\|dark\|rgb:R,G,B,tol] [--min-fraction 0.25] [--change] [--after S]` | first moment a region turns a color / changes | `event` |
| `offset --a SCREEN --a-roi R [--a-color C] --b SOUNDFILE [--b-after S] [--pre 0.5]` | the usual case: key lights in A, sound starts in B | `shift`, `trim.a_start`, `trim.b_start` |
| `align --a F --a-series K [--a-roi R] --b F --b-series K [--b-roi R] [--max-lag 3] [--metric corr\|mae]` | continuous matching (knob vs knob, knob vs sound) | `shift`, `score` |
| `verify FINAL --a-series K [--a-roi] --b-series K [--b-roi] [--tolerance-ms 40]` | check a finished video | `offset_ms`, `ok` |
| `series F --kind K [--roi R] --out x.csv\|x.npy` | inspect a signal | file written |

Series kinds: `knob` (angle of a rotary knob whose pointer is a color, default green; ROI = square around the knob), `motion` (frame-to-frame change in an ROI), `envelope` (loudness, dB), `brightness` (log spectral centroid; silence is NaN and skipped).

`align` picks `mae` automatically when both series are `knob` (same units) and `corr` otherwise.

## Recipes

**Screen + separately recorded sound, one key press per take**
```
r=$(eventsync offset --a take/phone.mp4 --a-roi 740,600,80,80 --b take/plugin.mov --pre 0.5)
# cut A from trim.a_start and B from trim.b_start, same duration; use B's audio
ffmpeg -ss <a_start> -t 10 -i phone.mp4 -ss <b_start> -t 10 -i plugin.mov -filter_complex "[0:v][1:v]hstack[v]" -map "[v]" -map 1:a out.mp4
```

**A knob moves in both views (most exact)**
```
eventsync align --a plugin.mov --a-series knob --a-roi 590,307,156,156 --b phone.mp4 --b-series knob --b-roi 430,144,156,156
# shift = +0.53 means the phone (B) at t+0.53 shows what the plugin (A) shows at t: start B 0.53 s later than A.
```

**Check the sound really follows the picture**
```
eventsync verify plugin.mov --a-series knob --a-roi 590,307,156,156 --b-series brightness   # ok, score ~0.9
```

**Final check** — on the composed file, measure the same thing from both halves of the frame (two ROIs in output coordinates) or a ROI against the audio. Report `offset_ms` to the user.

## Finding ROIs

1. `ffmpeg -ss <t> -i file -frames:v 1 frame.png` at a moment the element is visible, then look at it.
2. Note the file's real size (`ffprobe`): a 2× (Retina) window capture is twice the window's point size.
3. Keep the ROI tight around one element. For `knob`, a square centred on the knob, slightly larger than its face.
4. Before a long batch, test the ROI with `event` or `series` on one take.

## Pitfalls seen in practice

- Phone screen recordings (adb `screenrecord`) are variable frame rate; everything here resamples to `--fps` (30), so use the same `--fps` for both sides.
- A sound that starts with a slow attack is detected when it crosses -45 dBFS; for soft pads raise sensitivity (`--threshold-db -55`), for noisy rooms lower it.
- If a "key lights" event isn't found, check the color: try `--change`, or `rgb:R,G,B,40` sampled from the frame.
- A MOTION/automation playback keeps a knob moving: `align` on `knob` works far better there than a single onset.
- The latency differs per take (seen: 0.84–1.14 s on one Wi-Fi network in one evening). Never reuse one take's shift for another.
- Silence before the first note: `brightness` ignores it, but `envelope` doesn't. Prefer `brightness` or `onset`.
- **Verify the joined video, every clip, not the clips you joined.** Clips that were each in sync drifted once concatenated: each one's picture ran 0.13–0.2 s longer than its sound, so by the sixth clip the picture was 233 ms late. For each clip's time range in the final file, compare `event` on the key's output rectangle with `onset` (cut the range out first, or use `series` and look in the range). [promo-composer](https://github.com/sufystudios/promo-composer)'s `layout` command gives the output rectangle.

## Changing the code

- Core functions in `eventsync/core.py` (pure, numpy + ffmpeg pipes); CLI in `eventsync/cli.py`.
- Keep the JSON contract and exit codes stable; add fields, don't rename them.
- Add a test in `tests/test_eventsync.py` using `tests/synth.py` (generated media with known answers). Run `python3 -m unittest discover -s tests -v`; CI runs the same.
