"""Hardening tests: bad input, edge cases, and error paths."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from narrativediff.core import (
    Article,
    EventCorpus,
    analyze_event,
    load_corpus,
)
from narrativediff.cli import main


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write_json(data) -> str:
    """Write data to a temp JSON file; caller must unlink."""
    fh = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, fh)
    fh.close()
    return fh.name


def _run_cli(argv):
    """Run main() capturing stdout/stderr; returns (code, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = main(argv)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# core.load_corpus — input validation
# ---------------------------------------------------------------------------

class TestLoadCorpusValidation(unittest.TestCase):

    def test_articles_is_none_raises_clear_valueerror(self):
        """articles: null must raise ValueError with a clear message."""
        path = _write_json({"event": "test", "articles": None})
        try:
            with self.assertRaises(ValueError) as ctx:
                load_corpus(path)
            self.assertIn("articles", str(ctx.exception).lower())
        finally:
            os.unlink(path)

    def test_articles_is_string_raises_valueerror(self):
        """articles: 'oops' (string) must raise ValueError."""
        path = _write_json({"event": "test", "articles": "oops"})
        try:
            with self.assertRaises(ValueError):
                load_corpus(path)
        finally:
            os.unlink(path)

    def test_articles_is_dict_raises_valueerror(self):
        """articles: {} (dict, not list) must raise ValueError."""
        path = _write_json({"event": "test", "articles": {}})
        try:
            with self.assertRaises(ValueError):
                load_corpus(path)
        finally:
            os.unlink(path)

    def test_article_missing_outlet_raises_valueerror(self):
        """An article without 'outlet' key must raise ValueError with article index."""
        path = _write_json({
            "event": "test",
            "articles": [{"headline": "h", "body": "b"}],  # no outlet
        })
        try:
            with self.assertRaises(ValueError) as ctx:
                load_corpus(path)
            self.assertIn("#0", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_article_missing_headline_raises_valueerror(self):
        """An article without 'headline' key must raise ValueError."""
        path = _write_json({
            "event": "test",
            "articles": [{"outlet": "A", "body": "b"}],
        })
        try:
            with self.assertRaises(ValueError) as ctx:
                load_corpus(path)
            self.assertIn("#0", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_body_optional_defaults_to_empty(self):
        """An article without 'body' must succeed (body defaults to empty string)."""
        path = _write_json({
            "event": "no-body",
            "articles": [{"outlet": "A", "headline": "Headline Only"}],
        })
        try:
            corpus = load_corpus(path)
            self.assertEqual(len(corpus.articles), 1)
            self.assertEqual(corpus.articles[0].body, "")
        finally:
            os.unlink(path)

    def test_event_defaults_when_missing(self):
        """Missing 'event' key must not raise — defaults to a fallback string."""
        path = _write_json({
            "articles": [{"outlet": "A", "headline": "h", "body": "b"}],
        })
        try:
            corpus = load_corpus(path)
            self.assertIsInstance(corpus.event, str)
            self.assertTrue(corpus.event)  # non-empty
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# CLI — TypeError from malformed articles surfaces as a clean error
# ---------------------------------------------------------------------------

class TestCLIHardening(unittest.TestCase):

    def test_articles_null_gives_clean_error_not_traceback(self):
        """articles: null must produce exit 1 and a clean 'error:' message."""
        path = _write_json({"event": "test", "articles": None})
        try:
            code, _, err = _run_cli(["diff", path])
            self.assertEqual(code, 1)
            self.assertIn("error", err.lower())
            self.assertNotIn("Traceback", err)
        finally:
            os.unlink(path)

    def test_articles_string_gives_clean_error(self):
        """articles: 'bad' must produce exit 1, no traceback."""
        path = _write_json({"event": "test", "articles": "bad"})
        try:
            code, _, err = _run_cli(["diff", path])
            self.assertEqual(code, 1)
            self.assertIn("error", err.lower())
            self.assertNotIn("Traceback", err)
        finally:
            os.unlink(path)

    def test_outlets_missing_file_returns_2(self):
        """'outlets' sub-command also returns exit 2 on missing file."""
        code, _, err = _run_cli(["outlets", "no_such_file.json"])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_empty_articles_list_gives_clean_error(self):
        """An empty 'articles' list must produce exit 1 with a clear message."""
        path = _write_json({"event": "empty", "articles": []})
        try:
            code, _, err = _run_cli(["diff", path])
            self.assertEqual(code, 1)
            self.assertIn("error", err.lower())
            self.assertNotIn("Traceback", err)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# core.analyze_event — edge cases
# ---------------------------------------------------------------------------

class TestAnalyzeEdgeCases(unittest.TestCase):

    def test_single_article_no_crash(self):
        """A corpus with only one article must succeed (bias_spread == 0.0)."""
        corpus = EventCorpus(
            event="solo",
            articles=[Article("Solo", "A headline", "some body text here")],
        )
        result = analyze_event(corpus)
        self.assertEqual(result.outlet_count, 1)
        self.assertEqual(result.bias_spread, 0.0)
        self.assertEqual(result.most_favorable, result.most_unfavorable)

    def test_all_empty_bodies_no_crash(self):
        """Articles with empty body text must not crash."""
        corpus = EventCorpus(
            event="empty-bodies",
            articles=[
                Article("A", "", ""),
                Article("B", "", ""),
            ],
        )
        result = analyze_event(corpus)
        self.assertEqual(result.outlet_count, 2)
        for rep in result.reports:
            self.assertEqual(rep.word_count, 0)
            self.assertEqual(rep.bias_score, 0.0)

    def test_empty_corpus_raises_valueerror(self):
        """analyze_event on an empty articles list must raise ValueError."""
        with self.assertRaises(ValueError):
            analyze_event(EventCorpus(event="empty", articles=[]))

    def test_two_articles_divergence_ranking_length(self):
        """divergence_ranking length must match outlet_count."""
        corpus = EventCorpus(
            event="two",
            articles=[
                Article("Left", "shocking disaster", "reckless failure chaos"),
                Article("Right", "historic triumph", "bold successful breakthrough"),
            ],
        )
        result = analyze_event(corpus)
        self.assertEqual(len(result.divergence_ranking), 2)


if __name__ == "__main__":
    unittest.main()
