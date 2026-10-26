"""The /olx-brazil/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs). Caching lives here (cache.cached_call),
tofler-style: one ad page parse is cached per ad and served to details and
the batch call; one profile page parse per seller is shared by
sellers/details, sellers/ads (which needs the seller's uuid for a slug) and
sellers/reviews (which needs the numeric id's fallback ratings).
"""
import math
from concurrent.futures import ThreadPoolExecutor

from cache import cached_call
from olx_brazil import cache_config as ttl
from olx_brazil import fetch, parsers
from olx_brazil.fetch import OlxNotFound, OlxUpstreamError
from olx_brazil.refs import SITE, SELLER_ADS_SORT, SORT_QUERY, FILTER_QUERY_KEYS, UUID_RE
from olx_brazil.schemas import SEARCH_PAGE_SIZE, SELLER_ADS_PAGE_SIZE, MAX_SEARCH_PAGE
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

BATCH_WORKERS = 5


# ---- listing paths --------------------------------------------------------------

def _generated_path(filters):
    """The site's url-parser turns backend filters (a category code, a
    location id) into the friendly listing path; cached a week per set."""
    return cached_call("olx-brazil.url", {"filters": filters},
                       lambda filters: fetch.generate_url(filters), ttl.URL_CACHE)


def listing_path(category, location):
    """category: friendly path or numeric code (or None); location:
    {"path": ...} | {"filter": [key, value]} | None -> the listing path."""
    filters = {}
    category_path = location_path = None
    if category and category.isdigit():
        filters["search_category"] = category
    elif category:
        category_path = category
    if location:
        if location.get("path"):
            location_path = location["path"]
        elif location.get("filter"):
            key, value = location["filter"]
            filters[key] = value
    if filters:
        generated = _generated_path(filters)
        if category_path and "search_category" not in filters:
            generated = f"{category_path}/{generated}"
        if location_path and not any(k in filters for k in ("state", "region", "zone", "sd_id")):
            generated = f"{generated}/{location_path}"
        return generated
    return "/".join(p for p in (category_path, location_path) if p) or "brasil"


def _search_query(data):
    query = {}
    for name, value in (data.get("filters") or {}).items():
        query[name] = value
    for name, key in FILTER_QUERY_KEYS.items():
        value = data.get(name)
        if value is None:
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        query[key] = str(value)
    query.update(SORT_QUERY.get(data.get("sort") or "relevance", {}))
    query["q"] = data.get("query")
    if (data.get("page") or 1) > 1:
        query["o"] = str(data["page"])
    return query


# ---- ads/search ----------------------------------------------------------------

def _ads_search(**data):
    path = listing_path(data.get("category"), data.get("location"))
    query = _search_query(data)
    page = data.get("page") or 1
    listing = parsers.parse_listing(fetch.fetch_listing(path, query))
    total = listing.get("total_count") or 0
    total_pages = min(math.ceil(total / SEARCH_PAGE_SIZE), MAX_SEARCH_PAGE) if total else 0
    results = listing["results"] if (listing.get("page") or page) == page or page <= total_pages else []
    return {
        "query": data.get("query"),
        "sort": data.get("sort") or "relevance",
        "title": listing.get("title"),
        "link": fetch.listing_url(path, query),
        "category": listing.get("category"),
        "location": listing.get("location"),
        "breadcrumbs": listing.get("breadcrumbs"),
        "results": results,
        "pagination": {
            "page": page,
            "items_per_page": SEARCH_PAGE_SIZE,
            "total_pages": total_pages,
            "total_count": total,
        },
    }


def ads_search(**data):
    return cached_call("olx-brazil.search", data, _ads_search, ttl.SEARCH_CACHE)


# ---- ads/details (+ batch) ----------------------------------------------------------

def _ad_record(ad):
    record = parsers.parse_ad(fetch.fetch_ad(ad), ad)
    if record is None:
        raise OlxUpstreamError(f"ad {ad}: page without the ad payload")
    return record


def ad_details(ad):
    return cached_call("olx-brazil.ad", {"ad": ad}, _ad_record, ttl.AD_CACHE)


def _batch_item(ad):
    try:
        return ad_details(ad), None
    except NotFound as e:
        return None, {"ad": ad, "error": str(e) or "not found", "status": 404}
    except BadRequest as e:
        return None, {"ad": ad, "error": str(e), "status": 400}
    except (Blocked, UpstreamError) as e:
        return None, {"ad": ad, "error": str(e), "status": 502}


def ads_details_batch(ads):
    """Up to MAX_BATCH ads fetched in parallel; the ones that failed are
    reported in `errors` instead of failing the whole call."""
    with ThreadPoolExecutor(max_workers=min(BATCH_WORKERS, len(ads))) as pool:
        outcomes = list(pool.map(_batch_item, ads))
    results = [record for record, _ in outcomes if record is not None]
    errors = [error for _, error in outcomes if error is not None]
    return {"count": len(results), "results": results, "errors": errors}


# ---- sellers --------------------------------------------------------------------

def _profile_record(seller):
    record = parsers.parse_profile(fetch.fetch_profile(seller))
    if record is None:
        raise OlxNotFound(f"seller {seller} not found")
    record.pop("token", None)
    return record


def _profile(seller):
    return cached_call("olx-brazil.profile", {"seller": seller}, _profile_record, ttl.PROFILE_CACHE)


def _public_id(seller, profile=None):
    if UUID_RE.match(seller):
        return seller
    profile = profile or _profile(seller)
    public_id = (profile.get("seller") or {}).get("public_id")
    if not public_id:
        raise OlxUpstreamError(f"profile {seller} carries no public id")
    return public_id


def seller_details(seller):
    profile = _profile(seller)
    ads = profile.get("ads") or {}
    return {
        **profile["seller"],
        "history": profile.get("history"),
        "ratings": {
            "average": (profile.get("ratings") or {}).get("average"),
            "count": (profile.get("ratings") or {}).get("count"),
        },
        "ads_summary": {
            "total_count": ads.get("total_count"),
            "categories": ads.get("categories"),
            "states": ads.get("states"),
        },
        "recent_ads": ads.get("results"),
    }


def _seller_ads(seller, query, category, state, sort, page):
    public_id = _public_id(seller)
    payload = fetch.fetch_seller_ads(
        public_id, offset=(page - 1) * SELLER_ADS_PAGE_SIZE, limit=SELLER_ADS_PAGE_SIZE,
        sort=SELLER_ADS_SORT.get(sort or "newest", ""), category=category, state=state, search=query)
    parsed = parsers.parse_seller_ads(payload)
    total = parsed.get("total_count") or 0
    return {
        "seller": {"public_id": public_id, "link": f"{SITE}/perfil/{public_id}"},
        "query": query,
        "sort": sort or "newest",
        "categories": parsed.get("categories"),
        "states": parsed.get("states"),
        "results": parsed.get("results"),
        "pagination": {
            "page": page,
            "items_per_page": SELLER_ADS_PAGE_SIZE,
            "total_pages": math.ceil(total / SELLER_ADS_PAGE_SIZE) if total else 0,
            "total_count": total,
        },
    }


def seller_ads(**data):
    return cached_call("olx-brazil.seller_ads", data, _seller_ads, ttl.SELLER_ADS_CACHE)


def _seller_reviews(seller):
    profile = _profile(seller)
    public_id = _public_id(seller, profile)
    parsed = parsers.parse_reviews(fetch.fetch_reviews(public_id))
    profile_ratings = profile.get("ratings") or {}
    if parsed is None or (not parsed.get("reviews") and profile_ratings.get("reviews")):
        # the profile page carries the first ratings; use them when the
        # reviews app returns nothing for this id
        reviews = profile_ratings.get("reviews") or []
        parsed = {"average": profile_ratings.get("average"), "count": profile_ratings.get("count")
                  or len(reviews), "reviews": reviews}
    identity = profile.get("seller") or {}
    return {
        "seller": {
            "id": identity.get("id"),
            "public_id": public_id,
            "name": identity.get("name"),
            "link": identity.get("link"),
        },
        "average": parsed.get("average") if parsed.get("average") is not None else profile_ratings.get("average"),
        "count": parsed.get("count"),
        "reviews": parsed.get("reviews"),
    }


def seller_reviews(**data):
    return cached_call("olx-brazil.reviews", data, _seller_reviews, ttl.REVIEWS_CACHE)


# ---- search/suggestions, locations/search ----------------------------------------------

def _suggestions(query):
    results = parsers.parse_suggestions(fetch.fetch_suggestions(query))
    return {"query": query, "count": len(results), "results": results}


def search_suggestions(**data):
    return cached_call("olx-brazil.suggestions", data, _suggestions, ttl.SUGGEST_CACHE)


def _locations(query):
    results = parsers.parse_locations(fetch.fetch_locations(query))
    return {"query": query, "count": len(results), "results": results}


def locations_search(**data):
    return cached_call("olx-brazil.locations", data, _locations, ttl.LOCATIONS_CACHE)


# ---- categories --------------------------------------------------------------------

def _categories():
    tree = parsers.parse_categories(fetch.fetch_sitemap(), fetch.fetch_home())
    return {"count": len(tree), "categories": tree}


def categories_list(**data):
    return cached_call("olx-brazil.categories", data, _categories, ttl.CATEGORIES_CACHE)


def _category_filters(category):
    path = listing_path(category, None)
    listing = parsers.parse_listing(fetch.fetch_listing(path, {}))
    return {
        "category": listing.get("category"),
        "link": fetch.listing_url(path, {}),
        "total_count": listing.get("total_count"),
        "filters": parsers.parse_filters_template(listing.get("filters_template")),
    }


def category_filters(**data):
    return cached_call("olx-brazil.filters", data, _category_filters, ttl.FILTERS_CACHE)


# ---- vehicles/fipe -------------------------------------------------------------------

def _fipe(vehicle_type, brand):
    parsed = parsers.parse_fipe(fetch.fetch_fipe(vehicle_type, brand))
    if parsed is None:
        raise OlxUpstreamError("FIPE page without its data")
    parsed["link"] = f"{SITE}/tabela-fipe/{vehicle_type}" + (f"/{brand}" if brand else "")
    return parsed


def vehicles_fipe(**data):
    return cached_call("olx-brazil.fipe", data, _fipe, ttl.FIPE_CACHE)
