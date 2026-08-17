"""conform — prove the NON-DESTRUCTIVE guarantee: conforming an existing project never edits or
deletes the original's files; it only relocates `move` rows, refusing to overwrite, reversibly.

Hermetic: every test builds a throwaway project under tmp_path.
"""
import hashlib
import shutil
import subprocess

import pytest

import conform


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _make_project(root):
    """A messy legacy project: code, a notebook, data (incl. a raw dir), a figure, notes, cache."""
    (root / "analysis.py").write_text("print('fit model')\n")
    (root / "explore.ipynb").write_text('{"cells": []}\n')
    (root / "results.csv").write_text("a,b\n1,2\n")
    (root / "raw").mkdir()
    (root / "raw" / "cohort.csv").write_text("id,dx\n7,1\n")
    (root / "figures").mkdir()
    (root / "figures" / "roc.png").write_text("PNG-BYTES")
    (root / "FINDINGS.md").write_text("# we found a thing\n")
    (root / "README.md").write_text("legacy readme\n")
    (root / "requirements.txt").write_text("numpy\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("junk")


def _snapshot(root):
    return {str(p.relative_to(root)): _sha(p) for p in root.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------- #
# plan is a pure dry run                                                        #
# --------------------------------------------------------------------------- #
def test_plan_touches_no_original_content(tmp_path):
    _make_project(tmp_path)
    before = _snapshot(tmp_path)
    conform.plan(tmp_path)
    after = _snapshot(tmp_path)
    # every original file is byte-identical after planning (plan only ADDS its own audit/plan files)
    for rel, sha in before.items():
        assert after.get(rel) == sha, f"plan modified {rel}"
    assert (tmp_path / conform.PLAN_NAME).exists()
    assert (tmp_path / "notes" / "00_conformance_audit.md").exists()


def test_classification_is_sensible():
    root = None  # classify is pure on paths
    import pathlib
    root = pathlib.Path("/proj")
    assert conform.classify(root / "analysis.py", root)["action"] == "move"
    assert conform.classify(root / "analysis.py", root)["dest"].startswith("experiments/_unsorted/")
    assert conform.classify(root / "README.md", root)["action"] == "leave"
    assert conform.classify(root / "requirements.txt", root)["action"] == "leave"
    assert conform.classify(root / "__pycache__" / "x.pyc", root)["action"] == "skip"
    raw = conform.classify(root / "raw" / "cohort.csv", root)
    assert raw["action"] == "move" and "raw" in raw["dest"] and "read-only" in raw["reason"]


# --------------------------------------------------------------------------- #
# apply (copy strategy — non-git project): additive, originals kept            #
# --------------------------------------------------------------------------- #
def test_apply_copy_keeps_every_original(tmp_path):
    _make_project(tmp_path)
    before = _snapshot(tmp_path)
    conform.plan(tmp_path)
    res = conform.apply(tmp_path, force_method="copy")
    after = _snapshot(tmp_path)

    # GUARANTEE 1: no original was deleted and none was modified.
    for rel, sha in before.items():
        assert rel in after, f"copy strategy deleted {rel}"
        assert after[rel] == sha, f"copy strategy modified {rel}"

    # the research artifacts were copied to their staged destinations, byte-identical
    assert res["moved"], "expected some moves"
    for e in res["moved"]:
        assert e["method"] == "copy"
        assert (tmp_path / e["dst"]).exists()
        assert _sha(tmp_path / e["dst"]) == _sha(tmp_path / e["src"])

    # infra/cache were NOT moved
    dests = {e["dst"] for e in res["moved"]}
    assert not any("requirements.txt" in d for d in dests)
    assert not any(".pyc" in d for d in dests)


def test_apply_refuses_to_overwrite(tmp_path):
    _make_project(tmp_path)
    conform.plan(tmp_path)
    # pre-create a destination collision with DIFFERENT content
    dst = tmp_path / "experiments" / "_unsorted" / "analysis.py"
    dst.parent.mkdir(parents=True)
    dst.write_text("PRE-EXISTING DO NOT CLOBBER\n")
    guarded = _sha(dst)
    res = conform.apply(tmp_path, force_method="copy")
    # the colliding row is skipped, the pre-existing file is untouched, original still present
    assert any("analysis.py" in s["path"] for s in res["skipped"])
    assert _sha(dst) == guarded
    assert (tmp_path / "analysis.py").exists()


def test_undo_copy_removes_only_our_copies(tmp_path):
    _make_project(tmp_path)
    before = _snapshot(tmp_path)
    conform.plan(tmp_path)
    conform.apply(tmp_path, force_method="copy")
    conform.undo(tmp_path)
    after = _snapshot(tmp_path)
    # after undo, every original is still present & identical; the copies are gone
    for rel, sha in before.items():
        assert after.get(rel) == sha
    assert not (tmp_path / "experiments" / "_unsorted" / "analysis.py").exists()


# --------------------------------------------------------------------------- #
# apply (git mv strategy): a true, tracked, reversible move                     #
# --------------------------------------------------------------------------- #
def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_apply_git_mv_relocates_and_undo_restores(tmp_path):
    _make_project(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "legacy")
    src_sha = _sha(tmp_path / "analysis.py")

    conform.plan(tmp_path)
    res = conform.apply(tmp_path, force_method="git-mv")
    methods = {e["method"] for e in res["moved"]}
    assert methods == {"git-mv"} and res["moved"]
    # a tracked file is truly moved: original path gone, dest has identical content
    assert not (tmp_path / "analysis.py").exists()
    dst = tmp_path / "experiments" / "_unsorted" / "analysis.py"
    assert dst.exists() and _sha(dst) == src_sha

    conform.undo(tmp_path)
    assert (tmp_path / "analysis.py").exists()
    assert _sha(tmp_path / "analysis.py") == src_sha
    assert not dst.exists()


def test_apply_without_plan_errors(tmp_path):
    _make_project(tmp_path)
    with pytest.raises(conform.ConformError):
        conform.apply(tmp_path)


def test_safe_relocate_refuses_paths_outside_project(tmp_path):
    _make_project(tmp_path)
    with pytest.raises(conform.ConformError):
        conform.safe_relocate(tmp_path, "analysis.py", "../escape.py", prefer_git=False)
