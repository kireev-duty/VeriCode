"""Labels of the pair form: the report reads the published set, so scoring changes cannot orphan the labels."""

import json

from validation.labeling import LABELS_DIR, PAIRS_FILE, frozen_pairs, read_labels


def _write(path, version, labels):
    path.write_text(json.dumps({"version": version, "labeler": path.stem,
                                "labels": {k: {"rel": r, "comment": ""} for k, r in labels.items()}}), encoding="utf-8")


def test_read_labels_keeps_only_the_given_version(tmp_path):
    _write(tmp_path / "a.json", "v1", {"v0-c1": 3, "v0-c2": 0})
    _write(tmp_path / "b.json", "old", {"v0-c1": 1})
    _write(tmp_path / "c.json", "v1", {})
    assert read_labels("v1", tmp_path) == {"a": {"v0-c1": 3, "v0-c2": 0}}


def test_published_labels_match_the_published_set():
    pairs = frozen_pairs(world={})  # the published file exists, so the world is not needed
    ids = {c["pair_id"] for g in pairs["groups"] for c in g["candidates"]}
    assert len(ids) == pairs["pairs"]
    for f in LABELS_DIR.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d["version"] == pairs["version"], f"{f.name} was made on another form than {PAIRS_FILE.name}"
        assert set(d["labels"]) <= ids
