"""No response cache in the standalone scraper: every call goes to OLX Brazil
live. The API functions call cached_call(); here it simply runs the fetch.
Plug your own cache in here (Redis, a dict with expiry...) if you need one."""


def cached_call(namespace, data, fn, ttl, cache=True, refresh=False):
    """Run fn(**data) and return its result (namespace / ttl are ignored)."""
    return fn(**data)
