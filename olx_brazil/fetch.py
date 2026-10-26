"""OLX Brasil transport: plain curl_cffi with browser-impersonated TLS. No
browser, no login, no cookies kept. Egress: one sticky exit per thread
session (config.olx_brazil_proxy(), knob OLX_BRAZIL_EXIT); a retryable
failure drops the session, so the retry rides a fresh exit AND the next
TLS profile (IMPERSONATE_PROFILES).

Cloudflare in front of every olx.com.br host answers a flat "Sorry, you
have been blocked" 403 (no challenge, no clearance cookie) by exit IP and
TLS fingerprint: curl_cffi 0.16's "chrome" profile (Chrome 150) passed 7/7
residential exits on 2026-10-24 while the old chrome124 profile passed 2/7,
and "safari17_0" / "edge101" passed 7/7 — hence the profile rotation. The
machine this was researched from is on an IP block rule (403 even in real
Chrome); the tier that counts is the pod probe quoted in config.py.

Upstream surfaces (research 2026-10-23/24):

  * LISTING  GET www.olx.com.br/<category path>/<location path>?q=&o=<page>
             + the filter query strings — a Next.js app-router page whose
             ads (50 + featured slots per page) sit in the `self.__next_f`
             flight payload with pageIndex / totalOfAds / filtersTemplate /
             locations / breadcrumbs. Any page past 100 serves page 100.
             An unknown category path serves the HOME page (no listing
             payload) -> NotFound.
  * AD       GET www.olx.com.br/vi/<listId> (redirects to the regional
             host) — `<script id="initial-data" data-json="...">` blob.
             A removed / unknown ad answers HTTP 410.
  * PROFILE  GET www.olx.com.br/perfil/<uuid | slug> — Pages-router
             `__NEXT_DATA__` (seller, first 12 ads, history, ratings).
             Unknown seller -> a 4.8 KB "Ops!!" page with HTTP 200.
  * SELLER ADS  POST apigw.olx.com.br/profile-bff/token (header
             x-olxbr-profile-subject: <uuid>) -> viewer JWT (~24 h), then
             GET apigw.olx.com.br/profile-bff/auth/profile/v1/data?offset=
             &limit=&sort=&category=&state=&search= with the bearer. An
             unknown uuid -> HTTP 400 on the token call.
  * REVIEWS  GET avaliacoes.olx.com.br/vendedor/<uuid> — `__NEXT_DATA__`
             with the full ratings list (also answers the numeric sellerId).
  * SUGGEST  GET url-parser.olx.com.br/api/v1/search-suggestion/suggestion
             ?query= (header X-Slug-Version: v5)
  * LOCATE   GET location-autocomplete.olx.com.br/v2/location?q=
  * URL      POST url-parser.olx.com.br/api/v2/generate-url (X-Slug-Version
             v6, body [{name, value}]) -> {"url": "/<friendly path>"};
             an unknown category code -> 400 "Category N not found".
  * ATTRS    GET www.olx.com.br/api/filters/v1/attributes/<name>[?<parent>=]
  * FIPE     GET www.olx.com.br/tabela-fipe/<carros|motos>[/<brand>]
             (`__NEXT_DATA__`; unknown brand -> HTTP 404)
  * SITEMAP  GET www.olx.com.br/mapa-do-site (category tree) + the home page

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  OlxUpstreamError  transport failure / 5xx / unexpected shape — retryable
  OlxBlocked        403 / 429 / Cloudflare block page            — retryable
  OlxBadRequest     upstream 400 (unknown category code)         — never retried
  OlxNotFound       410 / 404 / "Ops" page / home-page fallback   — never retried
"""
import json
import os
import re
import sys
import threading
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from olx_brazil.refs import SITE

# Rotated on every retryable failure (see module docstring).
IMPERSONATE_PROFILES = ("chrome", "safari17_0", "edge101")
PAGE_TIMEOUT = 40      # listing pages are 0.6-1.8 MB through a residential exit
JSON_TIMEOUT = 20

API_HOST = "https://apigw.olx.com.br"
URL_PARSER = "https://url-parser.olx.com.br"
LOCATIONS = "https://location-autocomplete.olx.com.br"
REVIEWS = "https://avaliacoes.olx.com.br"
# The public key the profile app sends on its token call (profile bundle
# 650-535b9ee5c3af5535.js, 2026-10-23); the same value the ad page embeds
# as FAVORITES_API_SECRET.
PROFILE_TEAM_KEY = "xobt1DEOn8CblfaIFx5Ul5TNI0bKrZ0i"
SELLER_ADS_PATH = "/profile-bff/auth/profile/v1/data"

_TITLE_RE = re.compile(r"<title[^>]*>([^<]*)</title>", re.I)
_BLOCK_MARKERS = ("you have been blocked", "attention required! | cloudflare", "just a moment...")


class OlxUpstreamError(UpstreamError):
    """Transport failure / 5xx / unexpected payload — retryable."""


class OlxBlocked(OlxUpstreamError, Blocked):
    """403 / 429 or Cloudflare's block page — retryable on a fresh exit + profile."""


class OlxBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class OlxNotFound(NotFound):
    """Ad / seller / category / brand does not exist — never retried."""


# ---- sessions ----------------------------------------------------------------

_local = threading.local()
# Process-wide: after a block on the direct tier every new session rides the
# fallback exit (config.olx_brazil_fallback_proxy()) until this instant (config.OLX_BRAZIL_BLOCK_COOLDOWN).
_fallback_until = 0.0
_fallback_lock = threading.Lock()


def _proxy():
    """The exit for a new session: config.olx_brazil_proxy() (direct by
    default), or the fallback country's residential exit while a block
    cooldown is running."""
    proxy = config.olx_brazil_proxy()
    if proxy is None and time.time() < _fallback_until:
        proxy = config.olx_brazil_fallback_proxy()
    return proxy


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        idx = getattr(_local, "profile_idx", 0)
        proxy = _proxy()
        sess = curl_requests.Session(impersonate=IMPERSONATE_PROFILES[idx % len(IMPERSONATE_PROFILES)])
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        _local.session = sess
    return sess


def _drop_session(blocked=False):
    """Close the thread's session (fresh exit next time) and move to the next
    TLS profile; a block on the direct tier also starts the fallback cooldown."""
    global _fallback_until
    sess = getattr(_local, "session", None)
    _local.session = None
    _local.profile_idx = getattr(_local, "profile_idx", 0) + 1
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass
    if blocked and config.olx_brazil_proxy() is None:
        with _fallback_lock:
            _fallback_until = max(_fallback_until, time.time() + config.OLX_BRAZIL_BLOCK_COOLDOWN)


def _retrying(fn):
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except OlxUpstreamError as e:
            last = e
            _drop_session(blocked=isinstance(e, OlxBlocked))
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _page_title(text):
    match = _TITLE_RE.search(text or "")
    return match.group(1).strip() if match else ""


def _looks_blocked(text):
    head = (text or "")[:6000].lower()
    return any(marker in head for marker in _BLOCK_MARKERS)


def _classify(resp, label, not_found_statuses=(404, 410)):
    """Map an HTTP response to the taxonomy; return the body text."""
    if resp.status_code in not_found_statuses:
        raise OlxNotFound(f"{label} not found")
    if resp.status_code == 400:
        raise OlxBadRequest(resp.text[:200])
    if resp.status_code in (401, 403, 429):
        raise OlxBlocked(f"HTTP {resp.status_code} for {label}")
    if resp.status_code != 200:
        raise OlxUpstreamError(f"HTTP {resp.status_code} for {label}")
    if _looks_blocked(resp.text):
        raise OlxBlocked(f"block page for {label}")
    return resp.text


def _request(method, url, label, *, headers=None, timeout=JSON_TIMEOUT,
             not_found_statuses=(404, 410), **kw):
    try:
        resp = _session().request(method, url, headers=headers, timeout=timeout, **kw)
    except Exception as e:
        raise OlxUpstreamError(f"request failed: {type(e).__name__}: {e}")
    return _classify(resp, label, not_found_statuses), resp


PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}
JSON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": SITE,
    "referer": SITE + "/",
}


def _get_page(url, label, not_found_statuses=(404, 410)):
    def once():
        text, _ = _request("GET", url, label, headers=PAGE_HEADERS, timeout=PAGE_TIMEOUT,
                           not_found_statuses=not_found_statuses)
        return text
    return _retrying(once)


def _get_json(url, label, headers=None, not_found_statuses=(404,)):
    def once():
        text, resp = _request("GET", url, label, headers={**JSON_HEADERS, **(headers or {})},
                              not_found_statuses=not_found_statuses)
        try:
            return resp.json()
        except Exception:
            raise OlxUpstreamError(f"non-JSON {label} response: {text[:120]}")
    return _retrying(once)


# ---- listing / ad / profile pages ---------------------------------------------

def listing_url(path, query):
    """The listing URL for a friendly path ("celulares/estado-sp") and a dict
    of query strings (q, o, sf, ps, ...); empty values are dropped."""
    params = {k: v for k, v in (query or {}).items() if v not in (None, "", False)}
    url = f"{SITE}/{path.strip('/')}" if path else f"{SITE}/brasil"
    return url + ("?" + urlencode(params) if params else "")


# The site's own "relevance" sort key: a no-op on results, but any listing
# parameter turns a top-level category hub into its listing (below).
RELEVANCE_SORT = {"sp": "3"}


def _is_listing(html):
    return '"pageType":"listing"' in html or '"topazioQuery"' in html


def fetch_listing(path, query):
    """One listing page (HTML with the flight payload).

    Top-level category pages (/imoveis, /games, /eletronicos-e-celulares,
    ...) answer a hub page with no listing when the URL carries no listing
    parameter; the same URL with sp=3 (relevance, the default sort) is the
    listing (2026-10-26: /imoveis -> hub, /imoveis?sp=3 -> 6.38M ads). So a
    hub answer is retried once with sp=3. /autos-e-pecas stays a hub even
    with a keyword: only its subcategories list. An unknown category path
    serves the HOME page, which is NotFound too."""
    html = _get_page(listing_url(path, query), f"listing {path or 'brasil'}")
    if _is_listing(html):
        return html
    if "sp" not in query and "sf" not in query:
        html = _get_page(listing_url(path, {**query, **RELEVANCE_SORT}), f"listing {path or 'brasil'}")
        if _is_listing(html):
            return html
    raise OlxNotFound(f"no listing at /{path}: the category or location does not exist, or it is a "
                      "hub whose ads live in its subcategories (see /olx-brazil/categories/list)")


def fetch_ad(list_id):
    """The ad page HTML (initial-data blob). 410 = removed / unknown ad."""
    return _get_page(f"{SITE}/vi/{list_id}", f"ad {list_id}")


def fetch_profile(seller):
    """The seller profile HTML (__NEXT_DATA__); the "Ops!!" page = unknown."""
    html = _get_page(f"{SITE}/perfil/{seller}", f"seller {seller}")
    if "__NEXT_DATA__" not in html or _page_title(html).lower().startswith("ops"):
        raise OlxNotFound(f"seller {seller} not found")
    return html


def fetch_reviews(seller_id):
    """avaliacoes.olx.com.br/vendedor/<id> HTML (__NEXT_DATA__ ratings)."""
    html = _get_page(f"{REVIEWS}/vendedor/{seller_id}", f"seller {seller_id} reviews",
                     not_found_statuses=(404,))
    if "__NEXT_DATA__" not in html:
        raise OlxUpstreamError("reviews page without __NEXT_DATA__")
    return html


def fetch_fipe(vehicle_type, brand=None):
    """/tabela-fipe/<carros|motos>[/<brand>] HTML (__NEXT_DATA__)."""
    path = f"/tabela-fipe/{vehicle_type}" + (f"/{brand}" if brand else "")
    label = f"FIPE {vehicle_type}" + (f" brand {brand}" if brand else "")
    return _get_page(SITE + path, label)


def fetch_sitemap():
    return _get_page(f"{SITE}/mapa-do-site", "site map")


def fetch_home():
    return _get_page(f"{SITE}/", "home page")


# ---- JSON helpers ------------------------------------------------------------

def fetch_suggestions(query):
    """Search-box suggestions for a keyword (the site's own autocomplete)."""
    url = f"{URL_PARSER}/api/v1/search-suggestion/suggestion?{urlencode({'query': query})}"
    return _get_json(url, "suggestions", headers={"X-Slug-Version": "v5"})


def fetch_locations(query):
    """Location autocomplete (states, regions, cities, neighbourhoods)."""
    url = f"{LOCATIONS}/v2/location?{urlencode({'q': query})}"
    payload = _get_json(url, "locations")
    if not isinstance(payload, list):
        raise OlxUpstreamError(f"unexpected locations payload: {str(payload)[:120]}")
    return payload


def generate_url(filters):
    """The site's url-parser: a dict of backend filters (search_category,
    state, region, zone, sd_id, ...) -> the friendly listing path. An
    unknown category code is the site's 400 ("Category N not found")."""
    body = [{"name": name, "value": str(value)} for name, value in filters.items()
            if value not in (None, "")]

    def once():
        try:
            resp = _session().post(f"{URL_PARSER}/api/v2/generate-url", json=body,
                                   headers={**JSON_HEADERS, "X-Slug-Version": "v6",
                                            "content-type": "application/json"},
                                   timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OlxUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 400:
            message = ""
            try:
                message = resp.json().get("error") or ""
            except Exception:
                pass
            raise OlxNotFound(message or "category or location not found")
        text = _classify(resp, "url generation", not_found_statuses=(404,))
        try:
            path = resp.json().get("url")
        except Exception:
            raise OlxUpstreamError(f"non-JSON url-parser response: {text[:120]}")
        if not isinstance(path, str) or not path.startswith("/"):
            raise OlxUpstreamError(f"unexpected url-parser payload: {text[:120]}")
        return path.strip("/")
    return _retrying(once)


def fetch_attribute_values(attribute, parent=None):
    """/api/filters/v1/attributes/<attribute>[?<parent attribute>=<code>]."""
    url = f"{SITE}/api/filters/v1/attributes/{attribute}"
    if parent:
        url += "?" + urlencode(parent)
    payload = _get_json(url, f"attribute {attribute}")
    if not isinstance(payload, list):
        raise OlxUpstreamError(f"unexpected attribute payload: {str(payload)[:120]}")
    return payload


# ---- seller ads (profile-bff with a minted viewer token) -----------------------

_tokens = {}
_tokens_lock = threading.Lock()
TOKEN_SAFETY_SECS = 300


def _token_expiry(token):
    try:
        import base64
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp") or 0)
    except Exception:
        return 0


def fetch_profile_token(public_id, force=False):
    """A viewer JWT for one seller (cached until ~5 min before it expires).
    The site mints it cookie-less for any uuid; an unknown uuid is a 400."""
    now = time.time()
    with _tokens_lock:
        hit = _tokens.get(public_id)
        if hit and not force and hit[1] - TOKEN_SAFETY_SECS > now:
            return hit[0]

    def once():
        try:
            resp = _session().post(f"{API_HOST}/profile-bff/token", json={},
                                   headers={**JSON_HEADERS, "content-type": "application/json",
                                            "x-olxbr-profile-subject": public_id,
                                            "X-OLX-TEAM-KEY": PROFILE_TEAM_KEY},
                                   timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OlxUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 400:
            raise OlxNotFound(f"seller {public_id} not found")
        text = _classify(resp, "profile token", not_found_statuses=(404,))
        try:
            token = resp.json().get("access_token")
        except Exception:
            raise OlxUpstreamError(f"non-JSON token response: {text[:120]}")
        if not token:
            raise OlxUpstreamError(f"token response without access_token: {text[:120]}")
        return token
    token = _retrying(once)
    with _tokens_lock:
        _tokens[public_id] = (token, _token_expiry(token) or int(now) + 3600)
    return token


def fetch_seller_ads(public_id, offset=0, limit=50, sort="", category=None, state=None, search=None):
    """One page of a seller's ads from the profile BFF (the profile page's
    own infinite scroll). A 401 re-mints the token once."""
    params = {"offset": offset, "limit": limit, "sort": sort or ""}
    if category:
        params["category"] = category
    if state:
        params["state"] = state
    if search:
        params["search"] = search
    url = f"{API_HOST}{SELLER_ADS_PATH}?{urlencode(params)}"

    def once(force_token=False):
        token = fetch_profile_token(public_id, force=force_token)
        try:
            resp = _session().get(url, headers={**JSON_HEADERS, "authorization": f"Bearer {token}"},
                                  timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OlxUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if resp.status_code == 401 and not force_token:
            return once(force_token=True)
        text = _classify(resp, f"seller {public_id} ads", not_found_statuses=(404,))
        try:
            payload = resp.json()
        except Exception:
            raise OlxUpstreamError(f"non-JSON seller ads response: {text[:120]}")
        if not isinstance(payload, dict) or "content" not in payload:
            raise OlxUpstreamError(f"unexpected seller ads payload: {text[:120]}")
        return payload
    return _retrying(once)
