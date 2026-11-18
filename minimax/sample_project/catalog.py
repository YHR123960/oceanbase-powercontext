DATA = [{"id": 3, "status": "done"}, {"id": 1, "status": "open"}, {"id": 2, "status": "open"}]


def list_items(page=1, size=2, status=None):
    """Return catalog items, optionally filtered by status, with pagination."""
    if status is not None and status not in ("open", "done"):
        raise ValueError(f"Unsupported status: {status!r}")

    items = sorted(DATA, key=lambda item: item["id"])
    if status is not None:
        items = [item for item in items if item["status"] == status]

    return {
        "items": items[(page - 1) * size:page * size],
        "total": len(items),
    }
