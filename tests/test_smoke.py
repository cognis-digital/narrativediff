"""Smoke tests for NARRATIVEDIFF. Standard library only, no network."""
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from narrativediff import (  # noqa: E402
    Article,
    EventCorpus,
    analyze_event,
    load_corpus,
    TOOL_NAME,
    TOOL_VERSION,
)
from narrativediff.cli import main  # noqa: E402

DEMO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "demos", "01-basic", "event_rate_decision.json",
)


class TestCore(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(TOOL_NAME, "narrativediff")
        self.assertTrue(TOOL_VERSION)

    def test_empty_corpus_raises(self):
        with self.assertRaises(ValueError):
            analyze_event(EventCorpus(event="x", articles=[]))

    def test_bias_direction(self):
        corpus = EventCorpus(
            event="test",
            articles=[
                Article("Pos", "historic triumph",
                        "a bold successful breakthrough praised by all"),
                Article("Neg", "shocking disaster",
                        "a reckless failure that sparked chaos and outrage"),
                Article("Neutral", "bank sets rate",
                        "the bank set the rate today as scheduled"),
            ],
        )
        res = analyze_event(corpus)
        scores = {r.outlet: r.bias_score for r in res.reports}
        self.assertGreater(scores["Pos"], 0)
        self.assertLess(scores["Neg"], 0)
        self.assertEqual(res.most_favorable, "Pos")
        self.assertEqual(res.most_unfavorable, "Neg")

    def test_demo_corpus(self):
        corpus = load_corpus(DEMO)
        res = analyze_event(corpus)
        self.assertEqual(res.outlet_count, 5)
        outlets = {r.outlet for r in res.reports}
        self.assertIn("PopulistPost", outlets)
        # PopulistPost has the sensational ALL CAPS + ! headline.
        self.assertEqual(res.most_sensational, "PopulistPost")
        # Spread should be positive (favorable vs unfavorable outlets exist).
        self.assertGreater(res.bias_spread, 0)
        # Consensus facts should include shared tokens.
        joined = " ".join(res.consensus_facts)
        self.assertIn("rate", joined)

    def test_hedging_detected(self):
        corpus = load_corpus(DEMO)
        res = analyze_event(corpus)
        gl = next(r for r in res.reports if r.outlet == "GlobalLedger")
        # GlobalLedger is the hedge-heavy outlet.
        self.assertGreater(gl.hedge_rate, 0)

    def test_selective_omission(self):
        corpus = load_corpus(DEMO)
        res = analyze_event(corpus)
        # OppositionWatch omits the "vote"/"seven"/"two" detail others report.
        self.assertIn("OppositionWatch", res.selective_omissions)


class TestCLI(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            code = main(argv)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        return code, out.getvalue(), err.getvalue()

    def test_diff_table(self):
        code, out, _ = self._run(["diff", DEMO])
        self.assertEqual(code, 0)
        self.assertIn("PER-OUTLET BIAS", out)
        self.assertIn("DIVERGENCE", out)

    def test_diff_json(self):
        code, out, _ = self._run(["--format", "json", "diff", DEMO])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["outlet_count"], 5)
        self.assertIn("reports", data)

    def test_outlets(self):
        code, out, _ = self._run(["outlets", DEMO])
        self.assertEqual(code, 0)
        self.assertIn("EVENT:", out)

    def test_missing_file(self):
        code, _, err = self._run(["diff", "does_not_exist.json"])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_bad_json(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("{ not valid json")
            path = fh.name
        try:
            code, _, err = self._run(["diff", path])
            self.assertEqual(code, 1)
            self.assertIn("error", err)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
