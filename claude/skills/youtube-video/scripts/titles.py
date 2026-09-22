#!/usr/bin/env python3
"""Which title shapes travel, and how close a candidate sits to them.

Two questions, both answered from data already on disk rather than taste:

  1. Across a pool of niche videos, which structural features (a number, a bracket,
     "I did X", a question, a colon...) show up in the ones that beat their channel?
  2. For each candidate title, which real titles is it nearest to, and do those
     neighbours travel or flop?

Performance is views / subscribers — how far past its own audience a video went —
because raw views only measure how big the channel already was.

    titles.py pool.json                       # feature table + clusters
    titles.py pool.json --candidates c.txt    # + nearest neighbours per candidate

pool.json: [{"t": title, "v": views, "subs": subs}, ...] — build it from trends.py output.
No dependencies beyond numpy.
"""
import argparse, json, math, re, sys
from collections import Counter

import numpy as np

STOP = set("a an the of to in for on with and or is are be this that it its my your you i "
           "how what why when at from as by".split())

# Structural features. Each is a shape you could deliberately copy into a title.
FEATURES = {
    "number":      lambda t: bool(re.search(r"\b\d+", t)),
    "big number":  lambda t: bool(re.search(r"\b\d{3,}|\b\d+[kKxX]\b|\b\d+\s*(times|x)\b", t)),
    "bracket":     lambda t: bool(re.search(r"[\(\[].+?[\)\]]", t)),
    "colon":       lambda t: ":" in t,
    "question":    lambda t: t.strip().endswith("?"),
    "I did":       lambda t: bool(re.match(r"\s*(i|my|how i)\b", t, re.I)),
    "you/your":    lambda t: bool(re.search(r"\b(you|your)\b", t, re.I)),
    "vs":          lambda t: bool(re.search(r"\bvs\.?\b", t, re.I)),
    "free/steal":  lambda t: bool(re.search(r"\b(free|steal|no code|zero)\b", t, re.I)),
    "hype word":   lambda t: bool(re.search(r"\b(insane|crazy|finally|forever|breakthrough|"
                                            r"game ?changer|never|everything|ultimate|best|"
                                            r"biggest|kills?|destroys?|changed?)\b", t, re.I)),
    "time-bound":  lambda t: bool(re.search(r"\bin \d+\s*(min|minute|hour|second|day|week)", t, re.I)),
    "ALL CAPS":    lambda t: bool(re.search(r"\b[A-Z]{3,}\b", t)),
    "negation":    lambda t: bool(re.search(r"\b(not|nobody|don'?t|stop|isn'?t|can'?t|without)\b", t, re.I)),
    "superlative": lambda t: bool(re.search(r"\b(first|only|most|worst|fastest|cheapest)\b", t, re.I)),
}


def words(t):
    return [w for w in re.findall(r"[a-z0-9']+", t.lower()) if w not in STOP and len(w) > 2]


def tfidf(titles):
    docs = [words(t) for t in titles]
    vocab = sorted({w for d in docs for w in d})
    idx = {w: i for i, w in enumerate(vocab)}
    df = Counter(w for d in docs for w in set(d))
    n = len(docs)
    M = np.zeros((n, len(vocab)))
    for r, d in enumerate(docs):
        tf = Counter(d)
        for w, c in tf.items():
            M[r, idx[w]] = (c / len(d)) * math.log((1 + n) / (1 + df[w]) + 1)
    norm = np.linalg.norm(M, axis=1, keepdims=True)
    return M / np.where(norm == 0, 1, norm), vocab


def ratio(r):
    return (r["v"] / r["subs"]) if r.get("subs") else 0.0


def cmd_features(rows):
    rs = np.array([ratio(r) for r in rows])
    med = np.median(rs)
    print(f"{len(rows)} titles · median views/subs {med:.2f}\n")
    print(f"{'feature':<13} {'n':>4} {'median x':>9} {'lift':>7}")
    out = []
    for name, fn in FEATURES.items():
        hit = np.array([bool(fn(r["t"])) for r in rows])
        if hit.sum() < 3:
            continue
        m_in, m_out = np.median(rs[hit]), np.median(rs[~hit])
        lift = (m_in / m_out) if m_out else float("inf")
        out.append((lift, name, int(hit.sum()), m_in))
    for lift, name, n, m in sorted(out, reverse=True):
        bar = "+" * min(int(lift * 3), 24) if lift >= 1 else "-" * min(int(3 / max(lift, .01)), 10)
        print(f"{name:<13} {n:>4} {m:>9.2f} {lift:>6.2f}x  {bar}")
    print("\nlift = median views/subs WITH the feature, over WITHOUT it. Under ~5 titles, ignore it.")


def cmd_neighbours(rows, cands, k=4):
    all_t = [r["t"] for r in rows] + cands
    M, _ = tfidf(all_t)
    base, cand = M[:len(rows)], M[len(rows):]
    sims = cand @ base.T
    print("\n" + "=" * 78 + "\nCANDIDATES — nearest real titles, and how those travelled\n")
    for i, c in enumerate(cands):
        order = np.argsort(-sims[i])[:k]
        best = [(sims[i][j], rows[j]) for j in order if sims[i][j] > 0.01]
        feats = [n for n, fn in FEATURES.items() if fn(c)]
        print(f"» {c}")
        print(f"  features: {', '.join(feats) if feats else 'none'}")
        if not best:
            print("  nearest: nothing similar in the pool — this title is doing its own thing\n")
            continue
        for s, r in best:
            print(f"  {s:.2f}  {ratio(r):>6.1f}x  {r['v']:>9,}  {r['t'][:64]}")
        print(f"  neighbour median: {np.median([ratio(r) for _, r in best]):.1f}x\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("pool")
    p.add_argument("--candidates")
    a = p.parse_args()
    rows = [r for r in json.load(open(a.pool)) if r.get("t")]
    cmd_features(rows)
    if a.candidates:
        cands = [l.strip() for l in open(a.candidates) if l.strip() and not l.startswith("#")]
        cmd_neighbours(rows, cands)
