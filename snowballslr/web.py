"""Session API for the in-browser application.

The browser app (``docs/app/index.html``) runs this library in Pyodide inside a
Web Worker and drives it only through :class:`Session`. Every method takes and
returns plain JSON-compatible values, so the JavaScript side holds no review
logic: what the app shows is exactly what the library computed, and the whole
surface is tested on CPython in ``tests/test_web.py``.

A run lives in an ordinary run directory, in the browser's in-memory file
system. :meth:`Session.export_zip` packs it into a deterministic archive and
:meth:`Session.import_zip` unpacks one, so a run moves between the browser and
the command line (``snowballslr`` reads the extracted directory unchanged).
:func:`verify_archive` replays a received archive from its own cache with no
network access, which is the check a reviewer or editor runs.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config
from .core.run import Run

__all__ = ["ZIP_EPOCH", "Session", "verify_archive"]

# Fixed timestamp for archive members: an archive of the same run directory is
# then byte-identical whenever and wherever it is made.
ZIP_EPOCH = (2020, 1, 1, 0, 0, 0)
_ARCHIVE_ROOT = "run/"
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


def _work_dict(w: Any, score: float | None = None, rank: int | None = None) -> dict[str, Any]:
    authors = [f"{a.surname}, {a.given}" if a.given else a.surname for a in (w.authors or ())]
    directions = sorted({str(getattr(p.direction, "value", p.direction))
                         for p in (w.provenance or ())})
    return {
        "key": w.key, "title": w.title, "year": w.year, "doi": w.doi,
        "venue": w.venue, "authors": authors[:6], "n_authors": len(authors),
        "abstract": w.abstract, "type": w.type, "is_retracted": bool(w.is_retracted),
        "cited_by_count": w.cited_by_count, "directions": directions,
        "score": score, "rank": rank,
    }


def _safe_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    total, out = 0, []
    for info in zf.infolist():
        name = info.filename
        if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
            raise ValueError(f"unsafe path in archive: {name!r}")
        total += info.file_size
        if total > _MAX_ARCHIVE_BYTES:
            raise ValueError("archive expands beyond the 512 MB limit")
        out.append(info)
    return out


def _extract(data: bytes, dest: Path) -> Path:
    """Extract an archive and return the run directory inside it."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in _safe_members(zf):
            target = dest / info.filename
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
    candidates = [p.parent for p in dest.rglob("run.json")]
    if not candidates:
        raise ValueError("archive contains no run.json; is this a SnowBallSLR run?")
    return min(candidates, key=lambda p: len(p.parts))


def pack(run_dir: str | Path) -> bytes:
    """Deterministic zip of a run directory (sorted members, fixed timestamps)."""
    root = Path(run_dir)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.name.endswith((".lock", ".tmp")):
                continue
            info = zipfile.ZipInfo(_ARCHIVE_ROOT + p.relative_to(root).as_posix(), ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())
    return buf.getvalue()


def verify_archive(data: bytes) -> dict[str, Any]:
    """Replay an archived run from its own cache and compare with its manifest.

    No provider is contacted: verification is a pure function of the archive.
    """
    from .determinism.verify import verify_replay
    from .errors import VerificationError

    tmp = Path(tempfile.mkdtemp(prefix="snowballslr-verify-"))
    try:
        run_dir = _extract(data, tmp)
        try:
            report = verify_replay(run_dir, strict=False).to_dict()
        except VerificationError as exc:
            # Integrity failures that stop replay before artifacts can be compared
            # (a cache body whose content no longer matches its recorded hash, a
            # missing manifest entry) are results for the reviewer, not crashes.
            report = {"mode": "replay", "ok": False, "error": str(exc),
                      "artifacts_checked": 0, "artifacts_mismatched": []}
        manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        report["run"] = {
            "snowballslr_version": manifest.get("snowballslr_version"),
            "seeds": len(manifest.get("seeds") or []),
            "iterations": len(manifest.get("iterations") or []),
            "config_hash": manifest.get("config_hash"),
            "verified_with": __version__,
        }
        return report
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Session:
    """One review in progress. All arguments and results are JSON-compatible."""

    def __init__(self, workdir: str | Path | None = None) -> None:
        self.workdir = Path(workdir or tempfile.mkdtemp(prefix="snowballslr-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.run: Run | None = None

    # -- lifecycle ----------------------------------------------------------

    def new(
        self,
        seeds: Sequence[str] | str,
        config: Mapping[str, Any] | str | None = None,
        *,
        offline_graph: Mapping[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        if isinstance(seeds, str):
            seeds = [s.strip() for s in seeds.splitlines()
                     if s.strip() and not s.strip().startswith("#")]
        if not seeds:
            raise ValueError("no seed identifiers given")
        if isinstance(config, str):
            import yaml

            config = yaml.safe_load(config) or {}
        cfg = Config.from_dict(dict(config)) if config else Config()
        self.close()
        root = self.workdir / "run"
        if root.exists():
            shutil.rmtree(root)
        self.run = Run.init(root, list(seeds), cfg, offline_graph=offline_graph)
        return self.status() | {"seeds_requested": len(seeds)}

    def import_zip(self, data: bytes, *, offline_graph: Any = None) -> dict[str, Any]:
        self.close()
        dest = self.workdir / "imported"
        if dest.exists():
            shutil.rmtree(dest)
        run_dir = _extract(bytes(data), dest)
        self.run = Run.load(run_dir, offline_graph=offline_graph)
        return self.status()

    def export_zip(self) -> bytes:
        return pack(self._run().root)

    def close(self) -> None:
        if self.run is not None:
            self.run.close()
            self.run = None

    # -- the review loop ----------------------------------------------------

    def step(self) -> dict[str, Any]:
        run = self._run()
        works = run.step()
        scores = run.state.pending_scores
        # Same ordering as candidates.csv: descending score, key as tie-break.
        order = sorted(works, key=lambda w: (-scores.get(w.key, 0.0), w.key))
        cands = [_work_dict(w, scores.get(w.key), i + 1) for i, w in enumerate(order)]
        return self.status() | {"candidates": cands}

    def label(self, decisions: Mapping[str, str], *, allow_empty: bool = False) -> dict[str, Any]:
        self._run().label(dict(decisions), allow_empty=allow_empty)
        return self.status()

    def estimate(self) -> dict[str, Any]:
        est = self._run().estimate_recall()
        return est.to_dict() if hasattr(est, "to_dict") else dict(est)

    def report(self, graph: bool = False) -> dict[str, Any]:
        produced = self._run().report(prisma=True, graph=graph)
        out: dict[str, Any] = {}
        for name, path in sorted(produced.items()):
            p = Path(path)
            out[name] = (p.read_text(encoding="utf-8")
                         if p.suffix in (".md", ".json", ".svg", ".csv") else None)
        return out

    def status(self) -> dict[str, Any]:
        run = self._run()
        st = run.state
        return {
            "version": __version__,
            "iteration": st.iteration,
            "phase": str(getattr(st.phase, "value", st.phase)),
            "stopped": run.stopped,
            "stopped_by": st.stopped_by,
            "seeds": len(st.seeds),
            "included": len(st.included),
            "screened": sum(1 for v in st.decisions.values()
                            if str(getattr(v, "value", v)) in ("include", "exclude")),
            "pending": len(st.pending),
            "decisions": list(st.last_decisions),
            "openalex_key": bool(os.environ.get("OPENALEX_API_KEY")),
        }

    def _run(self) -> Run:
        if self.run is None:
            raise RuntimeError("no run: call new() or import_zip() first")
        return self.run
