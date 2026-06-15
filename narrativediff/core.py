"""Core engine for NARRATIVEDIFF.

Everything here is pure standard library and deterministic. The input is a
corpus of articles (each from an outlet) all covering one event. The output is
a structured diff describing bias, framing, and selective omission.

Lexicons below are small but real and hand-curated for media-bias analysis.
They are intentionally transparent so results are auditable.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Lexicons (auditable, hand-curated)
# ---------------------------------------------------------------------------

# Loaded / charged words mapped to a signed intensity. Negative = words that
# frame a subject unfavorably / alarmingly; positive = favorable / reassuring.
# Magnitude reflects how charged the term is.
LOADED_LEXICON: Dict[str, float] = {
    # negative / alarmist
    "slammed": -2.0, "blasted": -2.0, "chaos": -2.0, "crisis": -1.5,
    "disaster": -2.0, "shocking": -1.5, "outrage": -2.0, "outrageous": -2.0,
    "scandal": -2.0, "failed": -1.5, "failure": -1.5, "collapse": -2.0,
    "radical": -1.5, "extremist": -2.0, "reckless": -1.5, "botched": -2.0,
    "plunge": -1.5, "plunged": -1.5, "furious": -1.5,
    "alarming": -1.5, "threat": -1.0, "threatens": -1.0, "dangerous": -1.5,
    "controversial": -1.0, "backlash": -1.5, "meltdown": -2.0,
    "desperate": -1.5, "refused": -1.0, "admitted": -1.0, "forced": -1.0,
    "unprecedented": -1.0, "damning": -2.0, "devastating": -2.0,
    # positive / reassuring
    "historic": 1.5, "landmark": 1.5, "breakthrough": 1.5, "praised": 1.5,
    "hailed": 1.5, "triumph": 2.0, "success": 1.5, "successful": 1.5,
    "bold": 1.0, "decisive": 1.0, "reassured": 1.0, "calm": 1.0,
    "vowed": 0.5, "pledged": 0.5, "welcomed": 1.0, "celebrated": 1.5,
    "resilient": 1.0, "robust": 1.0, "strong": 0.5, "optimistic": 1.0,
}

# Hedging / uncertainty markers (high = more cautious / qualified reporting).
HEDGE_TERMS = {
    "reportedly", "allegedly", "apparently", "claims", "claimed", "suggests",
    "may", "might", "could", "reported", "sources", "unconfirmed",
    "according", "purportedly", "seemingly", "possibly",
}

# Attribution markers (signals sourcing rather than assertion).
ATTRIBUTION_TERMS = {
    "said", "stated", "told", "according", "announced", "confirmed",
    "explained", "noted", "added", "declared",
}

SENSATIONAL_PUNCT = re.compile(r"[!?]")

WORD_RE = re.compile(r"[a-z][a-z'-]+")

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "it", "its", "this", "that", "these", "those", "he",
    "she", "they", "them", "his", "her", "their", "has", "have", "had",
    "will", "would", "can", "could", "not", "no", "do", "does", "did",
    "who", "what", "which", "when", "where", "how", "than", "into", "over",
    "after", "before", "about", "out", "up", "down", "if", "so", "we",
    "you", "i", "our", "more", "most", "also", "said", "says",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Article:
    outlet: str
    headline: str
    body: str

    @property
    def full_text(self) -> str:
        return f"{self.headline}. {self.body}"


@dataclass
class EventCorpus:
    event: str
    articles: List[Article]


@dataclass
class OutletReport:
    outlet: str
    headline: str
    bias_score: float            # signed: <0 unfavorable framing, >0 favorable
    bias_magnitude: float        # absolute loaded-language intensity per 100 wd
    loaded_terms: List[Tuple[str, float]]
    hedge_rate: float            # hedges per 100 words
    attribution_rate: float      # attributions per 100 words
    sensationalism: float        # headline !?/caps score
    framing_keywords: List[str]  # distinctive terms (vs corpus)
    word_count: int


@dataclass
class DiffResult:
    event: str
    outlet_count: int
    reports: List[OutletReport]
    consensus_facts: List[str]   # tokens nearly all outlets share
    selective_omissions: Dict[str, List[str]]  # outlet -> notable terms others have
    bias_spread: float           # max-min bias_score
    most_favorable: str
    most_unfavorable: str
    most_sensational: str
    divergence_ranking: List[Tuple[str, float]]  # outlet -> distance from centroid


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------

def _tokens(text: str) -> List[str]:
    return WORD_RE.findall(text.lower())


def _content_tokens(text: str) -> List[str]:
    return [t for t in _tokens(text) if t not in STOPWORDS and len(t) > 2]


def _per_100(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count * 100.0 / total, 2)


# ---------------------------------------------------------------------------
# Per-outlet analysis
# ---------------------------------------------------------------------------

def _analyze_article(article: Article) -> Tuple[OutletReport, Dict[str, int]]:
    toks = _tokens(article.full_text)
    wc = len(toks)

    loaded: List[Tuple[str, float]] = []
    bias_sum = 0.0
    mag_sum = 0.0
    hedges = 0
    attributions = 0
    for t in toks:
        if t in LOADED_LEXICON:
            v = LOADED_LEXICON[t]
            loaded.append((t, v))
            bias_sum += v
            mag_sum += abs(v)
        if t in HEDGE_TERMS:
            hedges += 1
        if t in ATTRIBUTION_TERMS:
            attributions += 1

    # Sensationalism: punctuation in headline + ALLCAPS words in headline.
    hl = article.headline
    bangs = len(SENSATIONAL_PUNCT.findall(hl))
    caps_words = sum(
        1 for w in re.findall(r"[A-Za-z]{2,}", hl) if w.isupper()
    )
    sensational = round(bangs * 1.5 + caps_words * 1.0, 2)

    # Sort loaded terms by magnitude desc, dedup keep order.
    seen = set()
    loaded_sorted: List[Tuple[str, float]] = []
    for term, val in sorted(loaded, key=lambda x: -abs(x[1])):
        if term not in seen:
            seen.add(term)
            loaded_sorted.append((term, val))

    report = OutletReport(
        outlet=article.outlet,
        headline=article.headline,
        bias_score=round(_per_100(0, wc) + (bias_sum * 100.0 / wc if wc else 0), 3),
        bias_magnitude=round(mag_sum * 100.0 / wc if wc else 0.0, 3),
        loaded_terms=loaded_sorted[:12],
        hedge_rate=_per_100(hedges, wc),
        attribution_rate=_per_100(attributions, wc),
        sensationalism=sensational,
        framing_keywords=[],  # filled by corpus pass
        word_count=wc,
    )
    # term frequency of content tokens for framing / omission analysis
    tf: Dict[str, int] = {}
    for t in _content_tokens(article.full_text):
        tf[t] = tf.get(t, 0) + 1
    return report, tf


# ---------------------------------------------------------------------------
# Corpus-level analysis
# ---------------------------------------------------------------------------

def analyze_event(corpus: EventCorpus) -> DiffResult:
    if not corpus.articles:
        raise ValueError("corpus contains no articles")

    reports: List[OutletReport] = []
    tfs: List[Dict[str, int]] = []
    for art in corpus.articles:
        rep, tf = _analyze_article(art)
        reports.append(rep)
        tfs.append(tf)

    n = len(reports)

    # Document frequency across outlets for each content term.
    df: Dict[str, int] = {}
    for tf in tfs:
        for term in tf:
            df[term] = df.get(term, 0) + 1

    # Consensus facts: content terms present in >= ceil(0.8*n) outlets.
    threshold = math.ceil(0.8 * n)
    consensus = sorted(
        [t for t, c in df.items() if c >= threshold and c >= 2],
        key=lambda t: (-df[t], t),
    )[:25]

    # Framing keywords per outlet: terms the outlet uses that are rare in the
    # rest of the corpus (tf-idf style distinctiveness).
    for rep, tf in zip(reports, tfs):
        scored: List[Tuple[float, str]] = []
        for term, freq in tf.items():
            idf = math.log((n + 1) / (df[term])) + 1.0
            scored.append((freq * idf, term))
        scored.sort(key=lambda x: (-x[0], x[1]))
        rep.framing_keywords = [t for _, t in scored[:8]]

    # Selective omission: notable terms (in consensus or shared by majority)
    # that a given outlet does NOT mention.
    majority = math.ceil(0.5 * n)
    notable = {t for t, c in df.items() if c >= majority and c >= 2}
    omissions: Dict[str, List[str]] = {}
    for rep, tf in zip(reports, tfs):
        missing = sorted(
            [t for t in notable if t not in tf],
            key=lambda t: (-df[t], t),
        )
        if missing:
            omissions[rep.outlet] = missing[:10]

    # Bias spread + extremes.
    biases = [(r.outlet, r.bias_score) for r in reports]
    most_fav = max(biases, key=lambda x: x[1])[0]
    most_unfav = min(biases, key=lambda x: x[1])[0]
    bias_spread = round(
        max(b for _, b in biases) - min(b for _, b in biases), 3
    )
    most_sens = max(reports, key=lambda r: r.sensationalism).outlet

    # Divergence ranking: cosine distance of each outlet's content-vector from
    # the corpus centroid. Higher = covers the event most differently.
    vocab = sorted(df.keys())
    idx = {t: i for i, t in enumerate(vocab)}
    vectors: List[List[float]] = []
    for tf in tfs:
        v = [0.0] * len(vocab)
        for term, freq in tf.items():
            v[idx[term]] = float(freq)
        vectors.append(v)
    centroid = [0.0] * len(vocab)
    for v in vectors:
        for i, x in enumerate(v):
            centroid[i] += x
    centroid = [x / n for x in centroid]

    def _cos_dist(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 1.0
        return round(1.0 - dot / (na * nb), 4)

    divergence = sorted(
        [(rep.outlet, _cos_dist(v, centroid)) for rep, v in zip(reports, vectors)],
        key=lambda x: -x[1],
    )

    return DiffResult(
        event=corpus.event,
        outlet_count=n,
        reports=reports,
        consensus_facts=consensus,
        selective_omissions=omissions,
        bias_spread=bias_spread,
        most_favorable=most_fav,
        most_unfavorable=most_unfav,
        most_sensational=most_sens,
        divergence_ranking=divergence,
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_corpus(path: str) -> EventCorpus:
    """Load an event corpus from a JSON file.

    Expected shape:
        {"event": "...", "articles": [{"outlet":..,"headline":..,"body":..}, ...]}
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "articles" not in data:
        raise ValueError("corpus JSON must be an object with an 'articles' list")
    raw_articles = data["articles"]
    if not isinstance(raw_articles, list):
        raise ValueError(
            f"'articles' must be a JSON array, got {type(raw_articles).__name__}"
        )
    articles = []
    for i, a in enumerate(raw_articles):
        try:
            articles.append(
                Article(
                    outlet=str(a["outlet"]),
                    headline=str(a["headline"]),
                    body=str(a.get("body", "")),
                )
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"article #{i} is malformed: {exc}") from exc
    return EventCorpus(event=str(data.get("event", "untitled event")), articles=articles)


def result_to_dict(result: DiffResult) -> dict:
    d = asdict(result)
    # asdict turns tuples in divergence_ranking into lists already; ensure
    # loaded_terms tuples serialize cleanly.
    return d
