"""Build a real Scopus citation graph around the included studies of SYNERGY reviews.

For each review: the included studies (labels by the review's own authors, SYNERGY
dataset, CC0) are mapped to Scopus by DOI; for every included study the references
(Abstract Retrieval API, FULL view) and the citing works (Search API, REF(eid)) are
retrieved. Any snowballing run started from included seeds expands only included
studies, so this neighbourhood contains every candidate such a run can meet.

    SCOPUS_API_KEY=... SCOPUS_INSTTOKEN=... python synergy_scopus_crawl.py IDS_DIR OUT_DIR

IDS_DIR holds <review>_ids.csv files (openalex_id, doi, label_included, ...).
Writes OUT_DIR/<review>.json (resumable: finished reviews are skipped).
"""
from __future__ import annotations

import csv
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.elsevier.com/content"
H = {"X-ELS-APIKey": os.environ["SCOPUS_API_KEY"], "X-ELS-Insttoken": os.environ.get("SCOPUS_INSTTOKEN", ""),
     "Accept": "application/json", "User-Agent": "python-urllib"}
CALLS = {"search": 0, "abstract": 0}


def get(url, kind):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60) as r:
                CALLS[kind] += 1
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            if e.code == 404:
                return None
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:200]!r}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, json.JSONDecodeError):
            time.sleep(2 ** attempt)
    raise RuntimeError("retries exhausted")


def norm_doi(d):
    d = (d or "").strip().lower()
    for p in ("https://doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d or None


def search_all(query, cap=5000):
    out, start = [], 0
    while start < cap:
        q = urllib.parse.urlencode({"query": query, "count": 200, "start": start, "view": "STANDARD",
                                    "field": "eid,doi,dc:title,prism:coverDate,subtypeDescription"})
        b = get(f"{API}/search/scopus?{q}", "search")
        sr = (b or {}).get("search-results", {})
        ent = [e for e in sr.get("entry", []) if "error" not in e]
        out += ent
        start += 200
        if not ent or start >= int(sr.get("opensearch:totalResults", 0)):
            break
    return out, int(((b or {}).get("search-results", {}) or {}).get("opensearch:totalResults", 0) or 0)


def map_dois(dois):
    found = {}
    dois = sorted(dois)
    for i in range(0, len(dois), 20):
        part = dois[i:i + 20]
        q = " OR ".join(f'DOI("{d}")' for d in part)
        ent, _ = search_all(q, cap=200)
        for e in ent:
            d = norm_doi(e.get("prism:doi"))
            if d in part:
                found[d] = e
    return found


def full_record(eid):
    b = get(f"{API}/abstract/eid/{eid}?view=FULL", "abstract")
    if not b:
        return None
    a = b["abstracts-retrieval-response"]
    cd = a.get("coredata", {})
    refs = (((a.get("item") or {}).get("bibrecord") or {}).get("tail") or {}).get("bibliography") or {}
    refs = refs.get("reference") or []
    if isinstance(refs, dict):
        refs = [refs]
    out = []
    for r in refs:
        ri = r.get("ref-info") or {}
        ids = ri.get("refd-itemidlist", {}).get("itemid")
        ids = ids if isinstance(ids, list) else [ids] if ids else []
        sgr = next((x.get("$") for x in ids if x.get("@idtype") == "SGR"), None)
        doi = next((x.get("$") for x in ids if x.get("@idtype") == "DOI"), None)
        title = ((ri.get("ref-title") or {}).get("ref-titletext")) or ""
        year = (ri.get("ref-publicationyear") or {}).get("@first")
        if sgr:
            out.append({"eid": f"2-s2.0-{sgr}", "doi": norm_doi(doi), "title": title, "year": year})
    return {"eid": eid, "doi": norm_doi(cd.get("prism:doi")), "title": cd.get("dc:title") or "",
            "year": (cd.get("prism:coverDate") or "")[:4], "cited_by": int(cd.get("citedby-count") or 0),
            "references": out}


def crawl(review, ids_csv, out_dir):
    dst = out_dir / f"{review}.json"
    if dst.exists():
        return review, "skipped"
    with open(ids_csv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    inc = {norm_doi(r["doi"]) for r in rows if r["label_included"] == "1" and r["doi"]}
    allrec = {norm_doi(r["doi"]) for r in rows if r["doi"]}
    m = map_dois(inc)
    t_eids = {e["eid"]: d for d, e in m.items()}
    nodes = {}
    for eid in t_eids:
        rec = full_record(eid)
        if rec is None:
            continue
        cit, total = search_all(f"REF({eid})")
        rec["citing"] = [{"eid": e["eid"], "doi": norm_doi(e.get("prism:doi")), "title": e.get("dc:title") or "",
                          "year": (e.get("prism:coverDate") or "")[:4], "type": e.get("subtypeDescription")} for e in cit]
        rec["citing_total"] = total
        nodes[eid] = rec
    res = {"review": review, "n_records": len(rows), "n_included": sum(r["label_included"] == "1" for r in rows),
           "included_dois": sorted(inc), "included_mapped": t_eids, "record_dois": sorted(allrec),
           "expanded": nodes, "retrieved": time.strftime("%Y-%m-%d")}
    tmp = dst.with_suffix(".tmp")
    tmp.write_text(json.dumps(res))
    tmp.replace(dst)
    return review, f"{len(t_eids)}/{len(inc)} mapped, {len(nodes)} expanded"


if __name__ == "__main__":
    ids_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = sorted(ids_dir.glob("*_ids.csv"))
    with ThreadPoolExecutor(4) as ex:
        for review, msg in ex.map(lambda p: crawl(p.name[:-8], p, out_dir), jobs):
            print(review, msg, CALLS, flush=True)
