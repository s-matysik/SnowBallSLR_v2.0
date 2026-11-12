"""The browser session API, exercised on CPython against the offline fixture graph."""

import csv
import io
import json
import zipfile

import pytest

from snowballslr.core.run import Run
from snowballslr.determinism.verify import verify_replay
from snowballslr.web import Session, pack, verify_archive


def _drive(session, oracle, max_steps=8):
    for _ in range(max_steps):
        out = session.step()
        if out["stopped"] or not out["candidates"]:
            return out
        session.label({c["key"]: ("include" if c["key"] in oracle.included else "exclude")
                       for c in out["candidates"]})
    return session.status()


@pytest.fixture
def started(tmp_path, graph, seeds):
    s = Session(tmp_path / "w")
    s.new("\n".join(["# seeds", *seeds]), offline_graph=graph)
    return s


def test_status_is_json_serialisable(started):
    st = started.status()
    json.dumps(st)
    assert st["iteration"] == 0 and st["seeds"] >= 1 and not st["stopped"]


def test_candidates_match_the_exported_csv_order(started):
    out = started.step()
    it = out["iteration"]
    path = started.run.root / "iterations" / f"iter_{it:03d}" / "candidates.csv"
    with open(path, encoding="utf-8", newline="") as fh:
        csv_keys = [r["key"] for r in csv.DictReader(fh)]
    assert [c["key"] for c in out["candidates"]] == csv_keys
    assert [c["rank"] for c in out["candidates"]] == list(range(1, len(csv_keys) + 1))
    json.dumps(out)


def test_full_loop_stops_and_reports(started, oracle):
    final = _drive(started, oracle)
    assert final["stopped"] and final["stopped_by"]
    rep = started.report()
    assert "prisma.json" in rep and json.loads(rep["prisma.json"])
    assert rep["report.md"].startswith("#")


def test_archive_is_deterministic(started, oracle):
    _drive(started, oracle)
    a, b = started.export_zip(), started.export_zip()
    assert a == b
    names = zipfile.ZipFile(io.BytesIO(a)).namelist()
    assert names == sorted(names) and "run/run.json" in names


def test_round_trip_resumes_mid_review(tmp_path, graph, seeds, oracle):
    s1 = Session(tmp_path / "a")
    s1.new(seeds, offline_graph=graph)
    first = s1.step()
    s1.label({c["key"]: ("include" if c["key"] in oracle.included else "exclude")
              for c in first["candidates"]})
    archive = s1.export_zip()

    s2 = Session(tmp_path / "b")
    resumed = s2.import_zip(archive, offline_graph=graph)
    assert resumed["iteration"] == s1.status()["iteration"]
    assert resumed["included"] == s1.status()["included"]
    end2 = _drive(s2, oracle)

    end1 = _drive(s1, oracle)
    assert (end1["included"], end1["stopped_by"]) == (end2["included"], end2["stopped_by"])


def test_cli_reads_an_exported_run(tmp_path, started, oracle, graph):
    _drive(started, oracle)
    with zipfile.ZipFile(io.BytesIO(started.export_zip())) as zf:
        zf.extractall(tmp_path / "x")
    run = Run.load(tmp_path / "x" / "run", offline_graph=graph)
    assert run.stopped and verify_replay(tmp_path / "x" / "run").ok


def test_verify_archive_passes_and_detects_tampering(started, oracle):
    _drive(started, oracle)
    started.report()
    good = started.export_zip()
    rep = verify_archive(good)
    assert rep["ok"] and rep["artifacts_checked"] > 0 and rep["run"]["iterations"] >= 1

    src = zipfile.ZipFile(io.BytesIO(good))
    target = next(n for n in src.namelist() if n.endswith("candidates.csv"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for n in src.namelist():
            data = src.read(n)
            if n == target:
                data = data.replace(b"\n", b"\r\n", 1) + b"tampered\n"
            out.writestr(n, data)
    bad = verify_archive(buf.getvalue())
    assert not bad["ok"] and any("candidates.csv" in m for m in bad["artifacts_mismatched"])


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "run/../../x"])
def test_unsafe_archive_paths_rejected(tmp_path, name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, "x")
        zf.writestr("run/run.json", "{}")
    with pytest.raises(ValueError, match="unsafe"):
        Session(tmp_path).import_zip(buf.getvalue())


def test_not_a_run_rejected(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("notes.txt", "hello")
    with pytest.raises(ValueError, match=r"run\.json"):
        verify_archive(buf.getvalue())


def test_pack_skips_lock_files(tmp_path):
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "run.json").write_text("{}")
    (tmp_path / "r" / "state.lock").write_text("")
    names = zipfile.ZipFile(io.BytesIO(pack(tmp_path / "r"))).namelist()
    assert names == ["run/run.json"]


def test_methods_before_a_run_fail_clearly(tmp_path):
    with pytest.raises(RuntimeError, match="no run"):
        Session(tmp_path).status()


def test_verify_archive_reports_rather_than_raises(monkeypatch, started, oracle):
    import snowballslr.determinism.verify as v
    from snowballslr.errors import VerificationError

    _drive(started, oracle)
    archive = started.export_zip()

    def boom(*a, **k):
        raise VerificationError("cache entry body hash mismatch: abc")

    monkeypatch.setattr(v, "verify_replay", boom)
    rep = verify_archive(archive)
    assert rep["ok"] is False and "hash mismatch" in rep["error"]
