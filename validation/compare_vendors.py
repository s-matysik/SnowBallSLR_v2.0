# ruff: noqa: E702
"""Compare screening models from several providers against the review authors' decisions.

Expects in the namespace: SETD (records with review, doi, label), SW (scores dir), MODELS_ALL
(list of (label, provider, model_id)). Produces CMP (pooled metrics with bootstrap CIs on the
common subset), DIFF (paired AUC differences vs reference models), KAPPA, PERREV, COMMON.
"""
import json

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20261118)
NBOOT = 2000


def auc_fast(y, s):
    order = np.argsort(s, kind="mergesort")
    s_sorted = s[order]
    ranks = np.empty(len(s)); i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2 + 1
        i = j + 1
    r = np.empty(len(s)); r[order] = ranks
    npos = y.sum(); nneg = len(y) - npos
    return (r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)


def op(y, s, thr):
    p = s >= thr
    tp = (p & (y == 1)).sum(); fn = (~p & (y == 1)).sum(); tn = (~p & (y == 0)).sum(); fp = (p & (y == 0)).sum()
    sens, spec = tp / (tp + fn), tn / (tn + fp)
    return sens, spec, (tn + fn) / len(y) - (1 - sens)


def load_scores(SETD, SW, MODELS_ALL):
    D = SETD[["review", "doi", "label"]].copy()
    for lab, _prov, mid in MODELS_ALL:
        sc = json.loads((SW / f"scores_{mid}.json").read_text())
        D[lab] = D.doi.map(sc)
    return D


def bootstrap_idx(D):
    # stratified by review and label, so every resample keeps the design
    groups = [np.flatnonzero(m) for _, m in D.groupby(["review", "label"]).indices.items()] if False else \
             [idx for idx in D.groupby(["review", "label"]).indices.values()]
    for _ in range(NBOOT):
        yield np.concatenate([RNG.choice(g, len(g), replace=True) for g in groups])


def analyse(SETD, SW, MODELS_ALL, refs):
    D = load_scores(SETD, SW, MODELS_ALL)
    labs = [m[0] for m in MODELS_ALL]
    C = D.dropna(subset=labs).reset_index(drop=True)
    C["Ensemble, all models"] = C[labs].mean(axis=1)
    for prov in sorted({m[1] for m in MODELS_ALL}):
        cols = [m[0] for m in MODELS_ALL if m[1] == prov]
        C[f"Ensemble, {prov}"] = C[cols].mean(axis=1)
    allcols = [*labs, "Ensemble, all models"]
    y = C.label.values
    S = {c: C[c].values.astype(float) for c in allcols}
    point = {c: auc_fast(y, S[c]) for c in allcols}
    boots = {c: [] for c in allcols}
    for idx in bootstrap_idx(C):
        yb = y[idx]
        for c in allcols:
            boots[c].append(auc_fast(yb, S[c][idx]))
    boots = {c: np.array(v) for c, v in boots.items()}
    prov_of = {m[0]: m[1] for m in MODELS_ALL}
    rows = []
    for c in allcols:
        s5 = op(y, S[c], 5); s7 = op(y, S[c], 7)
        lo, hi = np.percentile(boots[c], [2.5, 97.5])
        rows.append(dict(model=c, provider=prov_of.get(c, "all"), n=len(C), auc=point[c], auc_lo=lo, auc_hi=hi,
                         sens5=s5[0], spec5=s5[1], wss5=s5[2], sens7=s7[0], spec7=s7[1]))
    CMP = pd.DataFrame(rows)
    drows = []
    for c in labs:
        for r in refs:
            if c == r:
                continue
            d = boots[c] - boots[r]
            lo, hi = np.percentile(d, [2.5, 97.5])
            p = 2 * min((d <= 0).mean(), (d >= 0).mean())
            drows.append(dict(model=c, reference=r, diff=point[c] - point[r], lo=lo, hi=hi, p_boot=min(1.0, p)))
    DIFF = pd.DataFrame(drows)
    K = pd.DataFrame(index=labs, columns=labs, dtype=float)
    for a in labs:
        for b in labs:
            pa, pb = S[a] >= 5, S[b] >= 5
            po = (pa == pb).mean(); pe = pa.mean() * pb.mean() + (1 - pa.mean()) * (1 - pb.mean())
            K.loc[a, b] = 1.0 if a == b else (po - pe) / (1 - pe)
    pr = []
    for rv, g in C.groupby("review"):
        yy = g.label.values
        for c in allcols:
            pr.append(dict(review=rv, model=c, auc=auc_fast(yy, g[c].values.astype(float)), sens5=op(yy, g[c].values.astype(float), 5)[0]))
    PERREV = pd.DataFrame(pr)
    ENSP = pd.DataFrame([dict(ensemble=c, auc=auc_fast(y, C[c].values.astype(float))) for c in C.columns if c.startswith("Ensemble, ")])
    return dict(D=D, COMMON=C, CMP=CMP, DIFF=DIFF, KAPPA=K, PERREV=PERREV, ENSP=ENSP, BOOTS=boots)
