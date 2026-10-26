"""Offline tests for the /olx-brazil/* request schemas and the listing
path / query builders in api.py (no network: the url-parser is stubbed).

    python -m pytest olx_brazil/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from olx_brazil import api, refs, schemas  # noqa: E402


def _errors(exc):
    return exc.value.normalized_messages()


# ---- ads/search ---------------------------------------------------------------

def test_search_schema_defaults():
    loaded = schemas.AdsSearchSchema().load({"query": " iphone 13 "})
    assert loaded["query"] == "iphone 13"
    assert loaded["sort"] == "relevance" and loaded["page"] == 1
    assert loaded["category"] is None and loaded["location"] is None
    assert loaded["filters"] is None


def test_search_schema_everything():
    loaded = schemas.AdsSearchSchema().load({
        "query": "civic", "category": "autos-e-pecas/carros-vans-e-utilitarios", "location": "RJ",
        "sort": "Newest", "seller_type": "professional", "price_min": "50000", "price_max": "90000",
        "year_min": "2018", "year_max": "2022", "mileage_max": "50000", "gearbox": "automatic",
        "fuel": "flex", "filters": "cf=5,ctp=9", "page": "3"})
    assert loaded["category"] == "autos-e-pecas/carros-vans-e-utilitarios"
    assert loaded["location"] == {"path": "estado-rj"}
    assert loaded["sort"] == "newest" and loaded["seller_type"] == "c"
    assert loaded["gearbox"] == "2" and loaded["fuel"] == "3"
    assert loaded["filters"] == {"cf": "5", "ctp": "9"}
    assert loaded["page"] == 3


def test_search_schema_accepts_codes_and_ids():
    loaded = schemas.AdsSearchSchema().load({"category": "3060", "location": "zone-2143"})
    assert loaded["category"] == "3060" and loaded["location"] == {"filter": ["zone", "2143"]}


def test_search_schema_allows_no_params():
    assert schemas.AdsSearchSchema().load({})["query"] is None
    assert schemas.AdsSearchSchema().load({"query": "  "})["query"] is None      # ?query= is "not given"
    assert schemas.SellerAdsSchema().load({"seller": "marcelo-810fa2d0", "query": ""})["query"] is None


@pytest.mark.parametrize("params,field", [
    ({"query": "x", "page": "101"}, "page"),
    ({"query": "x", "sort": "cheapest"}, "sort"),
    ({"query": "x", "price_min": "500", "price_max": "100"}, "price_max"),
    ({"query": "x", "year_min": "2020", "year_max": "2010"}, "year_max"),
    ({"query": "x", "rooms": "9"}, "rooms"),
    ({"query": "x", "filters": "gb"}, "filters"),
    ({"query": "x", "filters": "g b=2"}, "filters"),
    ({"query": "x", "location": "campinas"}, "location"),
    ({"query": "x", "category": "estado-sp"}, "category"),
    ({"query": "x", "url": "https://www.olx.com.br/brasil"}, "url"),      # no sibling params
])
def test_search_schema_rejects(params, field):
    with pytest.raises(ValidationError) as exc:
        schemas.AdsSearchSchema().load(params)
    assert field in _errors(exc)


def test_search_query_builder():
    data = schemas.AdsSearchSchema().load({
        "query": "civic", "sort": "newest", "seller_type": "private", "price_min": "1000", "price_max": "2000",
        "year_min": "2018", "gearbox": "automatic", "filters": "cf=5", "page": "2"})
    query = api._search_query(data)
    assert query == {"cf": "5", "ps": "1000", "pe": "2000", "f": "p", "rs": "2018", "gb": "2",
                     "sf": "1", "q": "civic", "o": "2"}


def test_listing_path_without_url_parser():
    assert api.listing_path(None, None) == "brasil"
    assert api.listing_path("celulares", None) == "celulares"
    assert api.listing_path(None, {"path": "estado-sp"}) == "estado-sp"
    assert api.listing_path("imoveis/venda", {"path": "estado-rj/rio-de-janeiro-e-regiao"}) == \
        "imoveis/venda/estado-rj/rio-de-janeiro-e-regiao"


def test_listing_path_with_url_parser(monkeypatch):
    calls = []

    def fake_generate(filters):
        calls.append(filters)
        if filters == {"search_category": "3060", "zone": "2143"}:
            return "celulares/estado-rj/rio-de-janeiro-e-regiao/zona-oeste"
        if filters == {"zone": "sd3460"}:
            return "estado-sp/grande-campinas/campinas"
        if filters == {"search_category": "2020"}:
            return "autos-e-pecas/carros-vans-e-utilitarios"
        raise AssertionError(filters)
    monkeypatch.setattr(api, "_generated_path", fake_generate)
    assert api.listing_path("3060", {"filter": ["zone", "2143"]}) == "celulares/estado-rj/rio-de-janeiro-e-regiao/zona-oeste"
    assert api.listing_path("celulares", {"filter": ["zone", "sd3460"]}) == "celulares/estado-sp/grande-campinas/campinas"
    assert api.listing_path("2020", {"path": "estado-sp"}) == "autos-e-pecas/carros-vans-e-utilitarios/estado-sp"
    assert len(calls) == 3


# ---- ads/details (+ batch) -----------------------------------------------------------

def test_ad_schema():
    assert schemas.AdSchema().load({"ad": "1542267399"}) == {"ad": 1542267399}
    assert schemas.AdSchema().load(
        {"ad": "https://rj.olx.com.br/rio-de-janeiro-e-regiao/celulares/iphone-15-no-precinho-1542267399"}) == {"ad": 1542267399}
    with pytest.raises(ValidationError):
        schemas.AdSchema().load({"ad": "iphone"})
    with pytest.raises(ValidationError):
        schemas.AdSchema().load({})
    with pytest.raises(ValidationError):
        schemas.AdSchema().load({"ad": "1542267399", "id": "1542267399"})


def test_batch_schema():
    loaded = schemas.AdsBatchSchema().load({"ads": "1542267399, https://www.olx.com.br/vi/1532599934,1542267399"})
    assert loaded == {"ads": [1542267399, 1532599934]}
    with pytest.raises(ValidationError) as exc:
        schemas.AdsBatchSchema().load({"ads": ",".join(str(1000000 + i) for i in range(11))})
    assert "At most 10" in str(_errors(exc)["ads"])
    with pytest.raises(ValidationError) as exc:
        schemas.AdsBatchSchema().load({"ads": "1542267399,abc"})
    assert "'abc'" in str(_errors(exc)["ads"])
    with pytest.raises(ValidationError):
        schemas.AdsBatchSchema().load({"ads": " , "})


# ---- sellers -----------------------------------------------------------------------

def test_seller_schema():
    assert schemas.SellerSchema().load({"seller": "810FA2D0-5B96-4981-A0A6-620667353479"}) == \
        {"seller": "810fa2d0-5b96-4981-a0a6-620667353479"}
    assert schemas.SellerSchema().load({"seller": "https://www.olx.com.br/perfil/marcelo-810fa2d0"}) == \
        {"seller": "marcelo-810fa2d0"}
    with pytest.raises(ValidationError) as exc:
        schemas.SellerSchema().load({"seller": "173778320"})
    assert "numeric user id" in str(_errors(exc)["seller"])
    with pytest.raises(ValidationError):
        schemas.SellerSchema().load({"seller": "marcelo"})


def test_seller_ads_schema():
    loaded = schemas.SellerAdsSchema().load({"seller": "marcelo-810fa2d0", "sort": "Lowest_Price",
                                             "category": "2020", "state": "1", "query": "bmw", "page": "2"})
    assert loaded == {"seller": "marcelo-810fa2d0", "sort": "lowest_price", "category": 2020, "state": 1,
                      "query": "bmw", "page": 2}
    defaults = schemas.SellerAdsSchema().load({"seller": "marcelo-810fa2d0"})
    assert defaults["sort"] == "newest" and defaults["page"] == 1 and defaults["query"] is None
    with pytest.raises(ValidationError):
        schemas.SellerAdsSchema().load({"seller": "marcelo-810fa2d0", "state": "28"})
    with pytest.raises(ValidationError):
        schemas.SellerAdsSchema().load({"seller": "marcelo-810fa2d0", "sort": "oldest"})
    assert refs.SELLER_ADS_SORT[defaults["sort"]] == ""


# ---- suggestions / locations / categories / fipe --------------------------------------------

def test_query_schemas():
    assert schemas.SearchSuggestionsSchema().load({"query": " iph "}) == {"query": "iph"}
    assert schemas.LocationsSearchSchema().load({"query": "Campinas"}) == {"query": "Campinas"}
    for cls in (schemas.SearchSuggestionsSchema, schemas.LocationsSearchSchema):
        with pytest.raises(ValidationError):
            cls().load({})
        with pytest.raises(ValidationError):
            cls().load({"query": "x" * 101})


def test_categories_schemas():
    assert schemas.CategoriesListSchema().load({}) == {}
    with pytest.raises(ValidationError):
        schemas.CategoriesListSchema().load({"page": "2"})
    assert schemas.CategoryFiltersSchema().load({"category": "2020"}) == {"category": "2020"}
    assert schemas.CategoryFiltersSchema().load(
        {"category": "https://www.olx.com.br/autos-e-pecas/motos/estado-sp"}) == {"category": "autos-e-pecas/motos"}
    with pytest.raises(ValidationError):
        schemas.CategoryFiltersSchema().load({})


def test_fipe_schema():
    assert schemas.FipeSchema().load({}) == {"vehicle_type": "carros", "brand": None}
    assert schemas.FipeSchema().load({"vehicle_type": "Motos", "brand": "Honda"}) == {"vehicle_type": "motos", "brand": "honda"}
    with pytest.raises(ValidationError):
        schemas.FipeSchema().load({"vehicle_type": "caminhoes"})
    with pytest.raises(ValidationError):
        schemas.FipeSchema().load({"brand": "fi at"})


# ---- category hubs (fetch_listing) ------------------------------------------------------

def test_fetch_listing_retries_a_category_hub_with_relevance_sort(monkeypatch):
    from olx_brazil import fetch
    hub = "<html><title>Imóveis | OLX</title></html>"
    listing = '<script>self.__next_f.push([1,"{\\"pageType\\":\\"listing\\"}"])</script> "pageType":"listing"'
    seen = []

    def fake_get_page(url, label, not_found_statuses=(404, 410)):
        seen.append(url)
        return listing if "sp=3" in url else hub
    monkeypatch.setattr(fetch, "_get_page", fake_get_page)
    assert fetch.fetch_listing("imoveis", {}) == listing
    assert seen == ["https://www.olx.com.br/imoveis", "https://www.olx.com.br/imoveis?sp=3"]


def test_fetch_listing_hub_without_listing_is_not_found(monkeypatch):
    from olx_brazil import fetch
    calls = []
    monkeypatch.setattr(fetch, "_get_page", lambda url, label, not_found_statuses=(404, 410): calls.append(url) or "<html></html>")
    with pytest.raises(fetch.OlxNotFound) as exc:
        fetch.fetch_listing("autos-e-pecas", {})
    assert "subcategories" in str(exc.value) and len(calls) == 2
    calls.clear()
    with pytest.raises(fetch.OlxNotFound):
        fetch.fetch_listing("autos-e-pecas", {"sf": "1"})       # a sort already set: no second try
    assert len(calls) == 1
