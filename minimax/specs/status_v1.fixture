# Catalog specification V1
Task: status-filter
list_items(page=1, size=2, status=None) returns {items, total}.
Sort ascending by id, filter before pagination, total counts filtered rows.
None preserves all original behavior. Allowed statuses: open, done.
An unsupported status (including empty string) raises ValueError.
Data entries must not be mutated.
