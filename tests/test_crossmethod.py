"""Cross-method recall: database-included studies and citation-included studies as arms."""

from types import SimpleNamespace

import pytest

from snowballslr.estimate.crossmethod import cross_method_estimate, parse_doi_list
from snowballslr.types import Decision
from snowballslr.web import Session


def _state(seeds, included, excluded=()):
    works = {k: SimpleNamespace(doi=k.split(":", 1)[1]) for k in [*seeds, *included, *excluded]}
    dec = {k: Decision.INCLUDE for k in [*seeds, *included]} | {k: Decision.EXCLUDE for k in excluded}
    return SimpleNamespace(seeds=list(seeds), works=works, decisions=dec)


def test_parse_csv_ris_and_plain_lines():
    csv_text = "\ufeffTitle,DOI\nA,10.1/AA\nB,\nC,https://doi.org/10.1/cc\n"
    assert parse_doi_list(csv_text) == ({"10.1/aa", "10.1/cc"}, 1)
    ris = "TY  - JOUR\nDO  - 10.1/x\nER  - \nTY  - JOUR\nTI  - none\nER  - \n"
    assert parse_doi_list(ris) == ({"10.1/x"}, 1)
    lines = "# included\n10.1000/p1\nsee https://doi.org/10.1016/q.2\nno doi here\n"
    assert parse_doi_list(lines) == ({"10.1000/p1", "10.1016/q.2"}, 1)
    assert parse_doi_list("DOI\n10.1/a\n\n10.1/b\n") == ({"10.1/a", "10.1/b"}, 0)
    semi = "Title;DOI\nA;10.1/s\n"
    assert parse_doi_list(semi) == ({"10.1/s"}, 0)


def test_seeds_are_removed_from_both_arms():
    seeds = [f"doi:10.1/s{i}" for i in range(3)]
    chase = [f"doi:10.1/c{i}" for i in range(40)]
    database = [d.split(":", 1)[1] for d in seeds] + [f"10.1/c{i}" for i in range(20)] + \
        [f"10.1/d{i}" for i in range(20)]
    r = cross_method_estimate(_state(seeds, chase), database)
    assert r["seeds_removed"] == 3 and r["n_database"] == 40 and r["n_citation"] == 40
    assert r["m"] == 20 and r["n_observed"] == 60
    # Chapman: 41 * 41 / 21 - 1
    assert r["n_hat"] == pytest.approx(41 * 41 / 21 - 1, abs=0.1)
    assert r["recall_combined"] == pytest.approx(60 / (41 * 41 / 21 - 1), abs=1e-3)
    assert not r["warnings"]


def test_records_without_doi_lower_the_estimate():
    seeds = ["doi:10.1/s"]
    chase = [f"doi:10.1/c{i}" for i in range(30)]
    db = ["10.1/s"] + [f"10.1/c{i}" for i in range(15)] + [f"10.1/d{i}" for i in range(15)]
    base = cross_method_estimate(_state(seeds, chase), db)
    worse = cross_method_estimate(_state(seeds, chase), db, database_without_doi=5)
    assert worse["recall_combined"] < base["recall_combined"]
    assert any("without a DOI" in w for w in worse["warnings"])


def test_seeds_missing_from_the_database_are_flagged():
    r = cross_method_estimate(_state(["doi:10.1/s"], [f"doi:10.1/c{i}" for i in range(9)]),
                              [f"10.1/c{i}" for i in range(5)] + ["10.1/z"])
    assert any("not in the database set" in w for w in r["warnings"])


def test_session_cross_method(tmp_path, graph, oracle):
    s = Session(tmp_path / "w")
    seeds = sorted(oracle.included)[:3]
    s.new("\n".join(seeds), offline_graph=graph)
    out = s.step()
    s.label({c["key"]: ("include" if c["key"] in oracle.included else "exclude")
             for c in out["candidates"]})
    inc = sorted(oracle.included)
    text = "DOI\n" + "\n".join(k.split(":", 1)[1] for k in inc[: len(inc) // 2] + seeds)
    r = s.cross_method(text)
    assert r["method"] == "cross_method_chapman" and r["seeds_removed"] == 3
    with pytest.raises(ValueError, match="no DOI"):
        s.cross_method("title only\nnothing\n")
