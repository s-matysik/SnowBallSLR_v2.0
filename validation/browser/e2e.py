"""End-to-end test of the browser app in a real Chromium (Playwright).

    python e2e.py SITE_DIR OUT_DIR [--live] [--channel chrome] [--proxy URL]

SITE_DIR holds app/ (index.html, the wheel, wheel.json, demo/) as published by
the documentation workflow. The test drives the offline demo to its stopping
rule by clicking the interface, downloads run.zip and the report, verifies the
archive in the app's reviewer mode, and with --live screens one backward
iteration against OpenAlex and Crossref. Writes OUT_DIR/e2e.json and screenshots.
"""
import argparse
import json
import mimetypes
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("site")
ap.add_argument("out")
ap.add_argument("--live", action="store_true")
ap.add_argument("--channel")
ap.add_argument("--proxy")
a = ap.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)

# The site is served by request interception rather than a local socket, so the
# test also runs where binding a port is not permitted.
ORIGIN = "https://snowballslr.test"
URL = f"{ORIGIN}/app/"
SITE = Path(a.site)


def serve(route):
    rel = route.request.url[len(ORIGIN) + 1:].split("?")[0]
    f = SITE / rel
    if f.is_dir():
        f = f / "index.html"
    if not f.is_file():
        return route.fulfill(status=404, body="not found")
    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    route.fulfill(status=200, body=f.read_bytes(), headers={"content-type": ctype})


res = {"console_errors": [], "steps": []}


def note(k, v):
    res[k] = v
    print(f"  {k}: {v}", flush=True)


def wait_ready(page):
    t0 = time.time()
    page.goto(URL)
    page.wait_for_selector("#startBtn:not([disabled])", timeout=300_000)
    return round(time.time() - t0, 1)


def idle(page, timeout=300_000):
    """Wait until the app has finished the action it is performing."""
    page.wait_for_function("() => !document.body.dataset.busy", timeout=timeout)


def screen_loop(page, include, max_rounds=12):
    """Click through iterations until the review stops; returns per-iteration counts."""
    rounds = []
    for _ in range(max_rounds):
        page.wait_for_selector("#screen:not(.hidden), #state:not(.hidden)", timeout=240_000)
        if page.is_visible("#screen"):
            n = page.locator("#cands .cand").count()
            inc = page.evaluate(f"""() => {{ let k = 0; document.querySelectorAll('#cands .cand').forEach(r => {{
                const hit = ({include})(r); r.querySelector(hit ? '.inc' : '.exc').click(); if (hit) k++; }}); return k; }}""")
            rounds.append({"iteration": int(page.inner_text("#itNo")), "candidates": n, "included": inc})
            if len(rounds) == 1:
                page.screenshot(path=str(out / "screen.png"), full_page=False)
            page.click("#submitBtn")
            idle(page)
        if page.is_visible("#nextBtn"):
            page.click("#nextBtn")
            idle(page)
            continue
        break
    return rounds


with sync_playwright() as p:
    kw = {"headless": True}
    if a.channel:
        kw["channel"] = a.channel
    if a.proxy:
        kw["proxy"] = {"server": a.proxy}
    browser = p.chromium.launch(**kw)
    ctx = browser.new_context(accept_downloads=True, viewport={"width": 1180, "height": 900})
    ctx.route(f"{ORIGIN}/**", serve)
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and res["console_errors"].append(m.text[:300]))
    page.on("dialog", lambda d: (res["steps"].append("dialog: " + d.message[:300]), d.dismiss()))

    note("boot_seconds", wait_ready(page))
    note("version", page.inner_text("#ver"))
    page.screenshot(path=str(out / "start.png"))

    # ---- offline demo, driven to its stopping rule -------------------------------
    page.click("#demoBtn")
    page.wait_for_function("document.querySelector('#seeds').value.includes('gold')")
    page.fill("#maxit", "10")
    page.click("#startBtn")
    idle(page)
    note("demo_rounds", screen_loop(page, "r => !!r.querySelector('a[href*=\"gold\"]')"))
    note("demo_final", page.inner_text("#stateBadge"))
    note("demo_stats", page.inner_text("#stats").replace("\n", " "))
    page.screenshot(path=str(out / "state.png"), full_page=True)
    page.click("#reportBtn")
    idle(page)
    page.wait_for_selector("#prisma svg", timeout=30_000)
    note("demo_estimate_line", page.locator("#reportOut p.hint").inner_text())
    with page.expect_download() as d:
        page.click("#zipBtn")
    d.value.save_as(out / "demo_run.zip")
    note("demo_zip_bytes", (out / "demo_run.zip").stat().st_size)

    # ---- reviewer mode: verify the archive just downloaded ------------------------
    page.click("button[data-tab=verify]")
    with page.expect_file_chooser() as fc:
        page.click("#verifyPick")
    fc.value.set_files(str(out / "demo_run.zip"))
    idle(page)
    page.wait_for_selector("#verifyOut .badge", timeout=30_000)
    note("verify_badge", page.inner_text("#verifyOut .badge"))
    note("verify_text", page.inner_text("#verifyOut p")[:200])
    page.screenshot(path=str(out / "verify.png"), full_page=True)

    # ---- live: one backward iteration against the real APIs ----------------------
    if a.live:
        page2 = ctx.new_page()
        page2.on("console", lambda m: m.type == "error" and res["console_errors"].append(m.text[:300]))
        page2.on("dialog", lambda d: (res["steps"].append("live dialog: " + d.message[:300]), d.dismiss()))
        page2.goto(URL)
        page2.wait_for_selector("#startBtn:not([disabled])", timeout=300_000)
        page2.click("button[data-tab=start]")
        page2.fill("#seeds", "10.1145/2601248.2601268")
        page2.uncheck("#dirF")
        page2.fill("#maxit", "1")
        t0 = time.time()
        page2.click("#startBtn")
        idle(page2)
        note("live_seconds_to_candidates", round(time.time() - t0, 1))
        if page2.is_visible("#screen"):
            note("live_candidates", page2.locator("#cands .cand").count())
            note("live_first_titles", [t[:80] for t in page2.locator("#cands .title").all_inner_texts()[:3]])
            page2.screenshot(path=str(out / "live_screen.png"))
            page2.evaluate("() => document.querySelectorAll('#cands .cand').forEach((r, i) => r.querySelector(i < 5 ? '.inc' : '.exc').click())")
            page2.click("#submitBtn")
            idle(page2)
            note("live_final", page2.inner_text("#stateBadge"))
            note("live_rules", page2.inner_text("#rules")[:400])
            with page2.expect_download() as d2:
                page2.click("#zipBtn")
            d2.value.save_as(out / "live_run.zip")
    browser.close()
(out / "e2e.json").write_text(json.dumps(res, indent=1))
print("console errors:", len(res["console_errors"]), "| dialogs:", res["steps"])
assert res.get("verify_badge") == "verified", res.get("verify_text")
assert "stopped" in res.get("demo_final", ""), res.get("demo_final")
