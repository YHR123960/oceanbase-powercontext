from copy import deepcopy
from sample_project.catalog import DATA, list_items

def test_default():
    assert list_items() == {"items": [{"id": 1, "status": "open"}, {"id": 2, "status": "open"}], "total": 3}

def test_pagination():
    assert list_items(page=2) == {"items": [{"id": 3, "status": "done"}], "total": 3}
    assert list_items(page=9)["items"] == []

def test_no_mutation():
    before = deepcopy(DATA)
    list_items()
    assert DATA == before
