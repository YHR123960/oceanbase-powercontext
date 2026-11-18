import pytest
from sample_project.catalog import list_items

@pytest.mark.parametrize("status,ids", [("open", [1, 2]), ("done", [3])])
def test_status(status, ids):
    result = list_items(status=status)
    assert [x["id"] for x in result["items"]] == ids
    assert result["total"] == len(ids)

def test_filter_before_page():
    assert list_items(page=2, size=1, status="open") == {"items": [{"id": 2, "status": "open"}], "total": 2}

@pytest.mark.parametrize("status", ["bad", "", "OPEN"])
def test_invalid(status):
    with pytest.raises(ValueError):
        list_items(status=status)
