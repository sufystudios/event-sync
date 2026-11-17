"""python3 -m unittest discover -s tests -v   (needs ffmpeg; makes its own media)"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth  # noqa: E402
from eventsync import core  # noqa: E402
from eventsync.cli import main  # noqa: E402

FRAME = 1 / synth.FPS


def roi(r):
    return ','.join(str(v) for v in r)


class EventSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.screen, cls.plugin = synth.make(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cli(self, *args):
        out = subprocess.run([sys.executable, '-m', 'eventsync', *args], capture_output=True, text=True,
                             cwd=os.path.dirname(HERE))
        return out.returncode, json.loads(out.stdout)

    def test_onset(self):
        self.assertAlmostEqual(core.audio_onset(self.plugin), synth.SOUND, delta=0.02)

    def test_onset_not_found(self):
        with self.assertRaises(core.EventNotFound):
            core.audio_onset(self.plugin, after=synth.SECONDS + 1)

    def test_color_event(self):
        t = core.color_event(self.screen, core.Roi(*synth.BUTTON), 'green')
        self.assertAlmostEqual(t, synth.PRESS, delta=FRAME + 0.001)

    def test_change_event(self):
        t = core.color_event(self.screen, core.Roi(*synth.BUTTON), change=True)
        self.assertAlmostEqual(t, synth.PRESS, delta=FRAME + 0.001)

    def test_offset_cli(self):
        code, r = self.run_cli('offset', '--a', self.screen, '--a-roi', roi(synth.BUTTON), '--b', self.plugin)
        self.assertEqual(code, 0, r)
        self.assertAlmostEqual(r['shift'], synth.LAG, delta=FRAME + 0.02)
        self.assertAlmostEqual(r['trim']['b_start'] - r['trim']['a_start'], r['shift'], delta=0.001)

    def test_knob_follows_the_drawing(self):
        s = core.knob_series(self.screen, core.Roi(*synth.KNOB))
        want = [synth.knob_angle(i / synth.FPS) for i in range(len(s))]
        self.assertLess(float(abs(s - want).mean()), 4.0)

    def test_align_two_knobs(self):
        code, r = self.run_cli('align', '--a', self.screen, '--a-series', 'knob', '--a-roi', roi(synth.KNOB),
                               '--b', self.plugin, '--b-series', 'knob', '--b-roi', roi(synth.KNOB))
        self.assertEqual(code, 0, r)
        self.assertEqual(r['metric'], 'mae')
        self.assertAlmostEqual(r['shift'], synth.LAG, delta=FRAME + 0.001)

    def test_sound_follows_its_knob(self):
        # In the plugin recording the knob and the sound's brightness move together.
        code, r = self.run_cli('verify', self.plugin, '--a-series', 'knob', '--a-roi', roi(synth.KNOB),
                               '--b-series', 'brightness', '--tolerance-ms', '70')
        self.assertEqual(code, 0, r)
        self.assertTrue(r['ok'])
        self.assertGreater(r['score'], 0.8)

    def test_verify_fails_when_out_of_sync(self):
        # The screen's knob against the plugin's sound is 0.9 s apart: verify on a side-by-side must fail.
        with tempfile.TemporaryDirectory() as d:
            both = os.path.join(d, 'both.mp4')
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', self.screen, '-i', self.plugin,
                            '-filter_complex', '[0:v][1:v]vstack[v]', '-map', '[v]', '-map', '1:a', both], check=True)
            code, r = self.run_cli('verify', both, '--a-series', 'knob', '--a-roi', roi(synth.KNOB),
                                   '--b-series', 'brightness')
            self.assertEqual(code, 3, r)
            self.assertFalse(r['ok'])
            self.assertAlmostEqual(r['shift'], synth.LAG, delta=3 * FRAME)

    def test_series_csv(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'knob.csv')
            self.assertEqual(main(['series', self.screen, '--kind', 'knob', '--roi', roi(synth.KNOB), '--out', out]), 0)
            self.assertTrue(open(out).readline().startswith('time,value'))

    def test_bad_color(self):
        code, r = self.run_cli('event', self.screen, '--roi', roi(synth.BUTTON), '--color', 'mauve')
        self.assertEqual(code, 1)
        self.assertEqual(r['error'], 'bad_input')


if __name__ == '__main__':
    unittest.main()
