#!/bin/sh
# Makes two test recordings with a known 0.9 s lag, then measures it three ways.
set -e
cd "$(dirname "$0")/.."
python3 -m tests.synth demo-media
python3 -m eventsync offset --a demo-media/screen.mp4 --a-roi 100,100,80,80 --b demo-media/plugin.mp4
python3 -m eventsync align --a demo-media/screen.mp4 --a-series knob --a-roi 400,80,160,160 \
                           --b demo-media/plugin.mp4 --b-series knob --b-roi 400,80,160,160
python3 -m eventsync verify demo-media/plugin.mp4 --a-series knob --a-roi 400,80,160,160 --b-series brightness
