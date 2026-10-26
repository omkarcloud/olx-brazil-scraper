"""Configuration for the OLX Brazil Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                       port the API listens on (default 8000)
    OLX_BRAZIL_PROXY           proxy URL for every request, e.g.
                               http://user:pass@host:port (default: none — direct).
                               OLX Brazil sits behind Cloudflare, which refuses
                               some IP ranges outright. If every call comes back
                               "blocked", your IP is one of them: set a residential
                               proxy (a Brazilian exit works best).
    OLX_BRAZIL_FALLBACK_PROXY  proxy URL used for OLX_BRAZIL_BLOCK_COOLDOWN seconds
                               after a block while OLX_BRAZIL_PROXY is unset
                               (default: none — keep retrying direct).

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request). Each retry
# opens a fresh connection and switches the browser TLS fingerprint.
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Seconds the fallback proxy is used after a block (direct mode only).
OLX_BRAZIL_BLOCK_COOLDOWN = 600


def olx_brazil_proxy():
    """The proxy every new session uses (None = direct)."""
    return os.environ.get("OLX_BRAZIL_PROXY") or None


def olx_brazil_fallback_proxy():
    """The proxy new sessions use for a while after a block (None = stay direct)."""
    return os.environ.get("OLX_BRAZIL_FALLBACK_PROXY") or None
