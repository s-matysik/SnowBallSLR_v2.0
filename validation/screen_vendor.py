# ruff: noqa: E701, E702
"""Score SYNERGY+ records with one model through an OpenAI-compatible or Gemini API.
    VENDOR=... MODEL=... API_KEY=... python screen_vendor.py SET.json PROMPT.txt OUT.json
Resumable: scores already in OUT.json are kept."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SET, PROMPT, OUT = json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]).read_text(), Path(sys.argv[3])
V, M, K = os.environ["VENDOR"], os.environ["MODEL"], os.environ["API_KEY"]
BASE = {"DEEPSEEK": "https://api.deepseek.com/v1", "KIMI": "https://api.moonshot.ai/v1", "OPENAI": "https://api.openai.com/v1", "XAI": "https://api.x.ai/v1"}
BATCH = 20
S = json.loads(OUT.read_text()) if OUT.exists() else {}
def call(prompt):
    for a in range(6):
        try:
            if V == "GOOGLE":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{M}:generateContent?key={K}"
                body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
                rq = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(rq, timeout=180) as r:
                    d = json.load(r); return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
            body = {"model": M, "messages": [{"role": "user", "content": prompt}]}
            if V == "DEEPSEEK": body["temperature"] = 0
            rq = urllib.request.Request(BASE[V] + "/chat/completions", data=json.dumps(body).encode(),
                                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {K}"})
            with urllib.request.urlopen(rq, timeout=300) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            msg = e.read()[:200]
            if e.code in (429, 500, 502, 503, 504): time.sleep(5 * 2 ** a); continue
            return "ERROR " + str(e.code) + " " + msg.decode("utf8", "replace")
        except Exception:
            time.sleep(5 * 2 ** a)
    return "ERROR retries"
def parse(t, n):
    m = re.search(r"\{.*\}", t or "", re.S)
    try: raw = json.loads(m.group()) if m else {}
    except Exception: return {}
    out = {}
    for k, v in raw.items():
        try:
            i = int(k)
            if 0 <= i < n: out[i] = float(v)
        except Exception: pass
    return out
def job(args):
    meta, recs = args
    items = "\n\n".join(f"[{i}] TITLE: {r['title']}\nABSTRACT: {r['abstract'][:1500]}" for i, r in enumerate(recs))
    t = call(PROMPT.format(title=meta["title"], criteria=meta["criteria"] or "(not stated; use the review title)", items=items))
    return recs, parse(t, len(recs)), t[:200] if t.startswith("ERROR") else ""
for _attempt in range(3):
    jobs = []
    for rv, meta in SET["reviews"].items():
        todo = [r for r in SET["records"] if r["review"] == rv and r["doi"] not in S]
        jobs += [(meta, todo[i:i + BATCH]) for i in range(0, len(todo), BATCH)]
    if not jobs: break
    errs = []
    with ThreadPoolExecutor(int(os.environ.get('THREADS', '6'))) as ex:
        for recs, sc, err in ex.map(job, jobs):
            for i, v in sc.items(): S[recs[i]["doi"]] = v
            if err: errs.append(err)
            OUT.write_text(json.dumps(S))
    if errs: print("errors:", len(errs), errs[0])
print(V, M, "scored", len(S), "of", len(SET["records"]))
