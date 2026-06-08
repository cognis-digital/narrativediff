# Demo 01 - Basic: one event, five outlets

This demo shows NARRATIVEDIFF comparing how five outlets covered the **same**
event: a central bank's surprise interest-rate decision.

The corpus (`event_rate_decision.json`) contains five articles. They report the
same core facts (the bank, the rate move, the vote) but differ sharply in
framing and loaded language:

- **WireService** — dry, attribution-heavy, near-neutral baseline.
- **MarketDaily** — favorable framing ("decisive", "reassured", "historic").
- **PopulistPost** — alarmist, sensational headline, "crisis/chaos/slammed".
- **GlobalLedger** — hedged, sourcing-driven ("reportedly", "sources").
- **OppositionWatch** — unfavorable, "reckless/failed", omits the vote detail.

## Run it

```bash
# Full diff (human-readable table)
python -m narrativediff diff demos/01-basic/event_rate_decision.json

# Machine-readable
python -m narrativediff --format json diff demos/01-basic/event_rate_decision.json

# Quick per-outlet bias scan
python -m narrativediff outlets demos/01-basic/event_rate_decision.json
```

## What to look for

- `bias_score`: PopulistPost / OppositionWatch go negative; MarketDaily positive.
- `most_sensational`: PopulistPost (headline punctuation + ALL CAPS).
- `selective_omissions`: OppositionWatch is flagged for skipping the vote split
  that every other outlet reports — a classic selective-omission signal.
- `divergence_ranking`: which outlet covers the event most differently from
  the consensus centroid.
- `consensus_facts`: the tokens nearly all outlets agree on (bank, rate, etc.).
