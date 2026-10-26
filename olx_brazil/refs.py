"""Reference resolvers + the small slug tables for /olx-brazil/*.

ONE param per input (tripadvisor QueryOrIdField convention): every id
param also takes the olx.com.br link of the same record. Resolvers raise
ValueError with a user-facing message (schema_fields.RefField -> 400).

Identifiers on olx.com.br (research 2026-10-23):
  * ad        `listId`, 6-12 digits, the trailing number of every ad link
              (https://sp.olx.com.br/<region>/<category>/<slug>-1542267399);
              https://www.olx.com.br/vi/<listId> serves the same page.
  * seller    `publicAccountId`, a UUID; the profile also answers the slug
              "<name>-<first 8 hex of the uuid>" (https://www.olx.com.br/perfil/
              marcelo-810fa2d0). The numeric userId does NOT open a profile.
  * category  the friendly path ("celulares", "autos-e-pecas/carros-vans-e-
              utilitarios", "imoveis/venda/casas") or the numeric code the
              site's filters use (3060, 2020, 1020); codes are turned into
              the path by the site's own url-parser (fetch.generate_url).
  * location  the path segments after the category ("estado-sp",
              "estado-sp/sao-paulo-e-regiao/zona-oeste"), a state code
              ("sp"), or a location id from /olx-brazil/locations/search
              ("state-1", "region-11", "zone-2143", "zone-sd3460",
              "sd_id-nb18278") — ids go through the url-parser as filters.
"""
import re
from urllib.parse import urlparse

SITE = "https://www.olx.com.br"
PROFILE_PATH = "/perfil/"

LIST_ID_RE = re.compile(r"^\d{6,12}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
PROFILE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{8}$", re.I)
CATEGORY_PATH_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*$")
CATEGORY_CODE_RE = re.compile(r"^\d{3,5}$")
STATE_CODE_RE = re.compile(r"^[a-z]{2}$", re.I)
LOCATION_PATH_RE = re.compile(r"^estado-[a-z]{2}(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*$")
# location ids as the site's autocomplete labels them: "<filter key>-<value>"
LOCATION_ID_RE = re.compile(r"^(state|region|zone|sd_id)-([a-z0-9]+)$", re.I)

_LINK_LIST_ID_RE = re.compile(r"(?:/vi/|-)(\d{6,12})(?:[/?#]|$)")
_LINK_PROFILE_RE = re.compile(r"/(?:perfil|vendedor)/([^/?#]+)")

# The 27 Brazilian states (the "estado-<uf>" path segment).
STATES = (
    "ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt",
    "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to",
)

# Public sort names -> the listing page's query string (the site's own
# "sp"/"sf" keys; observed 2026-10-24: sf=1 -> sort=date, sp=1 -> sort=price).
SORT_QUERY = {
    "relevance": {},
    "newest": {"sf": "1"},
    "lowest_price": {"sp": "1"},
}

# Seller-profile ad sorting (profile-bff `sort`, observed 2026-10-24: "" is
# newest first, "asc" / "desc" order by price).
SELLER_ADS_SORT = {"newest": "", "lowest_price": "asc", "highest_price": "desc"}

# Public choice -> listing query-string value (filtersTemplate, 2026-10-23).
# Seller type is the one filter whose template values lie: the filtersTemplate
# lists company_ad values 0/1, but the listing page maps f=0 / f=1 (and any
# other value) to company_ad=0. Only f=c gives company_ad=1 (verified
# 2026-10-26: "porsche 911" cars f=c -> 346 ads, 50/50 professional; f=1 ->
# 40 ads, 0 professional).
SELLER_TYPE = {"private": "p", "professional": "c"}
CONDITION = {"new": "1", "used_excellent": "2", "used_good": "3",
             "refurbished": "4", "defective": "5"}
GEARBOX = {"manual": "1", "automatic": "2", "semi_automatic": "3", "automated": "4"}
FUEL = {"gasoline": "1", "ethanol": "2", "flex": "3", "diesel": "5", "hybrid": "6", "electric": "7"}

# Short query-string key per public filter (the site's filtersTemplate).
FILTER_QUERY_KEYS = {
    "price_min": "ps", "price_max": "pe",
    "seller_type": "f", "condition": "elcd",
    "year_min": "rs", "year_max": "re", "mileage_min": "ms", "mileage_max": "me",
    "gearbox": "gb", "fuel": "fu",
    "rooms": "ros", "bathrooms": "bas", "garage_spaces": "gsp",
    "size_min": "ss", "size_max": "se",
}

FIPE_VEHICLE_TYPES = ("carros", "motos")


def _is_olx_host(url):
    host = (urlparse(url).hostname or "").lower()
    return host == "olx.com.br" or host.endswith(".olx.com.br")


def _as_url(value):
    if value.startswith(("http://", "https://", "//")):
        return value if not value.startswith("//") else "https:" + value
    return None


def resolve_ad(value):
    """Bare listId or any olx.com.br ad link -> the listId as an int."""
    value = (value or "").strip()
    if LIST_ID_RE.match(value):
        return int(value)
    url = _as_url(value)
    if url:
        if not _is_olx_host(url):
            raise ValueError("Must be an olx.com.br link.")
        match = _LINK_LIST_ID_RE.search(urlparse(url).path)
        if match:
            return int(match.group(1))
        raise ValueError("Must be an olx.com.br ad link (the link ends with the ad's "
                         "number, e.g. .../iphone-15-1542267399).")
    raise ValueError("Must be an ad id (the number at the end of the ad link, e.g. "
                     "1542267399) or an olx.com.br ad link.")


def resolve_seller(value):
    """Seller public id (UUID), profile slug (<name>-<8 hex>) or a
    www.olx.com.br/perfil/... (or avaliacoes.olx.com.br/vendedor/<uuid>) link
    -> the path segment the profile page takes."""
    value = (value or "").strip()
    url = _as_url(value)
    if url:
        if not _is_olx_host(url):
            raise ValueError("Must be an olx.com.br link.")
        match = _LINK_PROFILE_RE.search(urlparse(url).path)
        if not match:
            raise ValueError("Must be an olx.com.br seller profile link "
                             "(https://www.olx.com.br/perfil/<id>).")
        value = match.group(1)
    if UUID_RE.match(value):
        return value.lower()
    if PROFILE_SLUG_RE.match(value) and not value.isdigit():
        return value.lower()
    if value.isdigit():
        raise ValueError("A numeric user id does not open a profile; pass the seller's "
                         "public id (UUID) from /olx-brazil/ads/details, the profile "
                         "slug (name-xxxxxxxx) or the profile link.")
    raise ValueError("Must be a seller public id (UUID), a profile slug like "
                     "marcelo-810fa2d0, or an olx.com.br profile link.")


def resolve_category(value):
    """Friendly category path, a numeric category code, or a www.olx.com.br
    category link -> the path (lowercase, no slashes around) or the code."""
    value = (value or "").strip().lower()
    url = _as_url(value)
    if url:
        if not _is_olx_host(url):
            raise ValueError("Must be an olx.com.br link.")
        value = urlparse(url).path.strip("/")
        # a category link may carry a location tail: cut at the state segment
        value = value.split("/estado-", 1)[0]
    value = value.strip("/")
    if CATEGORY_CODE_RE.match(value):
        return value
    if (value and not value.isdigit() and CATEGORY_PATH_RE.match(value)
            and not value.startswith("estado-")):
        return value
    raise ValueError("Must be a category path (celulares, autos-e-pecas/carros-vans-e-"
                     "utilitarios, imoveis/venda) or a category code (3060); see "
                     "/olx-brazil/categories/list.")


def resolve_location(value):
    """State code, location path or location id -> {"path": ...} or
    {"filter": [key, value]} (the latter goes through the url-parser)."""
    value = (value or "").strip().lower()
    url = _as_url(value)
    if url:
        if not _is_olx_host(url):
            raise ValueError("Must be an olx.com.br link.")
        path = urlparse(url).path.strip("/")
        if "estado-" not in path:
            raise ValueError("The link carries no location (no estado-<uf> segment).")
        value = "estado-" + path.split("estado-", 1)[1]
    value = value.strip("/")
    if STATE_CODE_RE.match(value):
        if value not in STATES:
            raise ValueError(f"Unknown state code {value!r}; use one of: {', '.join(STATES)}.")
        return {"path": f"estado-{value}"}
    if LOCATION_PATH_RE.match(value):
        state = value.split("/", 1)[0][len("estado-"):]
        if state not in STATES:
            raise ValueError(f"Unknown state in {value!r}.")
        return {"path": value}
    match = LOCATION_ID_RE.match(value)
    if match:
        return {"filter": [match.group(1).lower(), match.group(2)]}
    raise ValueError("Must be a state code (sp), a location path (estado-sp/sao-paulo-e-"
                     "regiao) or a location id from /olx-brazil/locations/search "
                     "(zone-2143, region-11, state-1).")


def resolve_fipe_brand(value):
    """A FIPE brand slug (fiat, gm-chevrolet) or a /tabela-fipe/<type>/<brand> link."""
    value = (value or "").strip().lower()
    url = _as_url(value)
    if url:
        if not _is_olx_host(url):
            raise ValueError("Must be an olx.com.br link.")
        parts = [p for p in urlparse(url).path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "tabela-fipe":
            value = parts[2]
        else:
            raise ValueError("Must be a www.olx.com.br/tabela-fipe/<type>/<brand> link.")
    if value and re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", value):
        return value
    raise ValueError("Must be a FIPE brand slug (fiat, gm-chevrolet, vw-volkswagen) "
                     "from /olx-brazil/vehicles/fipe.")


def ad_link(list_id):
    return f"{SITE}/vi/{list_id}"


def profile_link(seller):
    return f"{SITE}{PROFILE_PATH}{seller}"
