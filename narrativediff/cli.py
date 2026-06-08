"""Command-line interface for NARRATIVEDIFF.

Subcommands:
  diff      Analyze a corpus JSON and emit the full bias/framing diff.
  outlets   List per-outlet bias one-liners (quick scan).

Global:
  --version           Print tool version and exit.
  --format {table,json}
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import analyze_event, load_corpus, result_to_dict


def _fmt_signed(x: float) -> str:
    return f"{x:+.2f}"


def _render_table(result_dict: dict) -> str:
    lines: List[str] = []
    lines.append(f"EVENT: {result_dict['event']}")
    lines.append(f"outlets analyzed: {result_dict['outlet_count']}")
    lines.append("")
    lines.append("PER-OUTLET BIAS & FRAMING")
    header = f"  {'OUTLET':<18}{'BIAS':>8}{'MAG':>7}{'HEDGE':>7}{'ATTR':>7}{'SENS':>6}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for r in result_dict["reports"]:
        lines.append(
            f"  {r['outlet'][:18]:<18}"
            f"{_fmt_signed(r['bias_score']):>8}"
            f"{r['bias_magnitude']:>7.2f}"
            f"{r['hedge_rate']:>7.2f}"
            f"{r['attribution_rate']:>7.2f}"
            f"{r['sensationalism']:>6.1f}"
        )
        if r["framing_keywords"]:
            lines.append(f"      frame: {', '.join(r['framing_keywords'][:6])}")
        if r["loaded_terms"]:
            terms = ", ".join(f"{t}({v:+g})" for t, v in r["loaded_terms"][:5])
            lines.append(f"      loaded: {terms}")
    lines.append("")
    lines.append("DIVERGENCE (distance from corpus centroid; higher = most different)")
    for outlet, dist in result_dict["divergence_ranking"]:
        bar = "#" * int(dist * 40)
        lines.append(f"  {outlet[:18]:<18}{dist:>7.3f}  {bar}")
    lines.append("")
    lines.append("SUMMARY")
    lines.append(f"  bias spread       : {result_dict['bias_spread']:+.2f}")
    lines.append(f"  most favorable    : {result_dict['most_favorable']}")
    lines.append(f"  most unfavorable  : {result_dict['most_unfavorable']}")
    lines.append(f"  most sensational  : {result_dict['most_sensational']}")
    lines.append("")
    lines.append("CONSENSUS FACTS (shared by >=80% of outlets)")
    lines.append("  " + (", ".join(result_dict["consensus_facts"]) or "(none)"))
    lines.append("")
    lines.append("SELECTIVE OMISSIONS (majority terms an outlet skips)")
    if result_dict["selective_omissions"]:
        for outlet, missing in result_dict["selective_omissions"].items():
            lines.append(f"  {outlet}: {', '.join(missing)}")
    else:
        lines.append("  (none detected)")
    return "\n".join(lines)


def _render_outlets(result_dict: dict) -> str:
    lines = [f"EVENT: {result_dict['event']}"]
    for r in sorted(result_dict["reports"], key=lambda x: x["bias_score"]):
        tag = "favorable" if r["bias_score"] > 0.2 else (
            "unfavorable" if r["bias_score"] < -0.2 else "neutral"
        )
        lines.append(
            f"  {r['outlet'][:20]:<20} {_fmt_signed(r['bias_score'])}  "
            f"[{tag}]  \"{r['headline'][:60]}\""
        )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="News bias & framing diff across many outlets per event.",
    )
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=["table", "json"], default="table",
                   help="output format (default: table)")
    sub = p.add_subparsers(dest="command", required=True)

    pd = sub.add_parser("diff", help="full bias/framing diff of a corpus JSON")
    pd.add_argument("corpus", help="path to event corpus JSON file")

    po = sub.add_parser("outlets", help="quick per-outlet bias one-liners")
    po.add_argument("corpus", help="path to event corpus JSON file")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        corpus = load_corpus(args.corpus)
        result = analyze_event(corpus)
    except FileNotFoundError:
        print(f"error: corpus file not found: {args.corpus}", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    result_dict = result_to_dict(result)

    if args.format == "json":
        print(json.dumps(result_dict, indent=2, ensure_ascii=False))
        return 0

    if args.command == "outlets":
        print(_render_outlets(result_dict))
    else:
        print(_render_table(result_dict))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
