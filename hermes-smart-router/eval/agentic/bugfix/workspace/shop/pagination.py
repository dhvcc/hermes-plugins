def page(items, number, size):
    """Items on 1-based page `number` of size `size`; an empty list past the last page."""
    start = number * size
    return items[start:start + size]


def page_count(total, size):
    """Number of pages needed for `total` items; 0 items need 0 pages."""
    return total // size
