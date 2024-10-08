from urllib.parse import urlencode


def qs_active(existing_qs, fltr, by):
    """Active when identical key/value in existing query string."""
    qs_set = {(fltr, by)}
    # Not active if either are empty.
    if not existing_qs or not qs_set:
        return False
    # See if the intersection of sets is the same.
    existing_qs_set = set(existing_qs.items())
    return existing_qs_set.intersection(qs_set) == qs_set


def qs_toggler(existing_qs, fltr, by):
    """Resolve filter against an existing query string."""
    qs = {fltr: by}
    # Don't change the currently rendering existing query string!
    rtn_qs = existing_qs.copy()
    # Test for identical key and value in existing query string.
    if qs_active(existing_qs, fltr, by):
        # Remove so that buttons toggle their own value on and off.
        rtn_qs.pop(fltr)
    else:
        # Update or add the query string.
        rtn_qs.update(qs)
    return urlencode(rtn_qs)
