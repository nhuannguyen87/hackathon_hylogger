"""Synthetic hole folders for nvcl_datasets.choose_dataset - no NVCL needed.

    python test_nvcl_datasets.py      (or pytest)
"""

import json
import tempfile
from pathlib import Path

import nvcl_datasets as nd

COLLAR = (-28.38, 127.44)  # (lat, lon) of borehole.json


def dataset(name, lat, lon, top, bottom):
    header = f"<TSGHeader><Latitude>{lat}</Latitude><Longitude>{lon}</Longitude></TSGHeader>"
    return {"dataset_id": f"id-{name}", "dataset_name": name, "description": header,
            "depth_from_m": top, "depth_to_m": bottom}


def folder(datasets, owners=True, hole="HOLE"):
    path = Path(tempfile.mkdtemp()) / hole
    path.mkdir()
    (path / "borehole.json").write_text(json.dumps({"y": COLLAR[0], "x": COLLAR[1]}))
    (path / "datasets.json").write_text(json.dumps(datasets))
    logs = [{"log_id": f"log-{d['dataset_name']}", **({"dataset_id": d["dataset_id"]} if owners else {})}
            for d in datasets]
    (path / "logs_scalar.json").write_text(json.dumps(logs))
    return path


def test_without_a_same_name_dataset_the_collar_beats_length():
    # no dataset is named like the folder: the one at borehole.json's collar
    # beats a longer namesake 1,250 km away
    choice = nd.choose_dataset(folder([dataset("BH01", -33.32, 115.66, 0, 900),
                                       dataset("BH01_Behemoth", *COLLAR, 163, 562)]))
    assert choice.name == "BH01_Behemoth"
    assert choice.owns("log-BH01_Behemoth") and not choice.owns("log-BH01")


def test_the_holes_own_name_beats_borehole_json():
    # the catalog's plain-name BH01 is the Bunbury bore; NVCL's borehole.json
    # for the folder describes the Behemoth namesake - the name wins
    choice = nd.choose_dataset(folder([dataset("BH01_Behemoth", *COLLAR, 163, 562),
                                       dataset("BH01", -33.32, 115.66, 18, 21.6)], hole="BH01"))
    assert choice.name == "BH01"


def test_core_beats_cuttings_at_the_same_collar():
    choice = nd.choose_dataset(folder([dataset("EGD002_chips", *COLLAR, 0.5, 99.5),
                                       dataset("EGD002", *COLLAR, 98.8, 333.4)]))
    assert choice.name == "EGD002"
    assert [d["dataset_name"] for d in choice.skipped] == ["EGD002_chips"]


def test_two_cores_at_one_collar_must_be_spliced_not_dropped():
    try:
        nd.choose_dataset(folder([dataset("15EIS001", *COLLAR, 0, 600),
                                  dataset("15EIS001_wedge", *COLLAR, 450, 800)]))
    except nd.SpliceNeeded as exc:
        assert "15EIS001_wedge" in str(exc)
    else:
        raise AssertionError("a main hole and its wedge were silently reduced to one")


def test_unrecorded_log_owners_stop_the_hole():
    try:
        nd.choose_dataset(folder([dataset("A", *COLLAR, 0, 10), dataset("B", 0, 0, 0, 10)], owners=False))
    except nd.DatasetsNotRecorded:
        pass
    else:
        raise AssertionError("mixed the logs of two datasets")


def test_log_owners_from_dataset_collection():
    xml = ("<DatasetCollection><Dataset><DatasetID>d1</DatasetID><Logs><Log><LogID>a</LogID></Log>"
           "<Log><LogID>b</LogID></Log></Logs></Dataset><Dataset><DatasetID>d2</DatasetID><Logs>"
           "<Log><LogID>c</LogID></Log></Logs></Dataset></DatasetCollection>")
    assert nd.log_owners(xml) == {"a": "d1", "b": "d1", "c": "d2"}
    assert nd.log_owners("") == {}


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)
