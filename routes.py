"""The 11 OLX Brazil endpoints. Every path is served with and without the
`/olx-brazil` prefix, so code generated against the hosted API on RapidAPI
(paths like /ads/details) runs unchanged against this server.

Params are validated by the same marshmallow schemas the hosted API uses
(olx_brazil/schemas.py): one param per input — `ad` takes an ad ID or an ad
link, `seller` a public ID, profile slug or profile link — and an unknown
param is a 400 that names it."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from olx_brazil import api, schemas
from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

PREFIX = "/olx-brazil"


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so a UTF-8 "São Paulo" would arrive mangled)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    host = request.get_header("Host") or "localhost"
    return f"{request.urlparts.scheme}://{host}{path}?{urlencode(query)}"


def paginate(result, path, params):
    """Lift the `pagination` block into the flat shape the hosted API returns:
    count / per_page / current_page / total_pages / next / previous."""
    pagination = result.pop("pagination", None) or {}
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, params, page + 1 if page < total_pages else None),
        "previous": _page_link(path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(schema_cls, fn, paginated=False):
    """Validate the query, run the endpoint, map failures to HTTP:
    bad params -> 400, unknown ad / seller / category -> 404,
    blocked or upstream failure -> 500."""
    raw = query_dict()
    data, error = load_query(schema_cls, raw)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"olx-brazil rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"olx-brazil blocked the request, retry later or set "
                                       f"OLX_BRAZIL_PROXY: {e}"}, 500)
    except UpstreamError as e:
        return json_response({"error": f"olx-brazil request failed: {e}"}, 500)
    except Exception as e:
        return json_response({"error": f"olx-brazil request failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


ENDPOINTS = [
    ("/ads/details", schemas.AdSchema, api.ad_details, False),
    ("/ads/search", schemas.AdsSearchSchema, api.ads_search, True),
    ("/ads/details/batch", schemas.AdsBatchSchema, api.ads_details_batch, False),
    ("/sellers/details", schemas.SellerSchema, api.seller_details, False),
    ("/sellers/ads", schemas.SellerAdsSchema, api.seller_ads, True),
    ("/sellers/reviews", schemas.SellerSchema, api.seller_reviews, False),
    ("/search/suggestions", schemas.SearchSuggestionsSchema, api.search_suggestions, False),
    ("/locations/search", schemas.LocationsSearchSchema, api.locations_search, False),
    ("/categories/list", schemas.CategoriesListSchema, api.categories_list, False),
    ("/categories/filters", schemas.CategoryFiltersSchema, api.category_filters, False),
    ("/vehicles/fipe", schemas.FipeSchema, api.vehicles_fipe, False),
]


def mount(path, schema_cls, fn, paginated):
    """Serve one endpoint at /path and /olx-brazil/path."""
    def handler():
        return call(schema_cls, fn, paginated)
    handler.__name__ = "olx_brazil_" + path.strip("/").replace("/", "_")
    route(path, method="GET")(handler)
    route(PREFIX + path, method="GET")(handler)


for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
