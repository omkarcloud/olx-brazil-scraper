"""Offline tests for the OLX Brasil parsers, reference resolvers and value
helpers.

    python -m pytest olx_brazil/test_parsers.py -q

Fixtures are real olx.com.br pages / JSON captured 2026-10-23/24
(olx_brazil/fixtures/): three listing pages, an empty search, the home page
the site serves for an unknown category, three ad pages (phone, car, house),
a removed ad (410), three profiles + the "Ops" not-found page, a profile BFF
page + a past-the-end page, a rated and an unrated reviews page, suggestion
/ location / attribute / url-parser JSON and the FIPE pages. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from olx_brazil import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


@pytest.fixture(scope="module")
def phones():
    return P.parse_listing(fixture("listing_phones_iphone.html"))


@pytest.fixture(scope="module")
def cars():
    return P.parse_listing(fixture("listing_cars_sp.html"))


@pytest.fixture(scope="module")
def houses():
    return P.parse_listing(fixture("listing_realestate_rj.html"))


@pytest.fixture(scope="module")
def car_ad():
    return P.parse_ad(fixture("ad_car.html"), 1532599934)


# ---- refs -------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("1542267399", 1542267399),
    (" 1542267399 ", 1542267399),
    ("https://rj.olx.com.br/rio-de-janeiro-e-regiao/celulares/iphone-15-no-precinho-1542267399", 1542267399),
    ("https://www.olx.com.br/vi/1542267399?x=1", 1542267399),
    ("//sp.olx.com.br/sao-paulo-e-regiao/autos-e-pecas/carros-vans-e-utilitarios/bmw-x1-2018-1532599934", 1532599934),
])
def test_resolve_ad(value, expected):
    assert refs.resolve_ad(value) == expected


@pytest.mark.parametrize("value", ["", "iphone", "123", "https://example.com/vi/1542267399",
                                   "https://www.olx.com.br/perfil/marcelo-810fa2d0"])
def test_resolve_ad_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_ad(value)


@pytest.mark.parametrize("value,expected", [
    ("810fa2d0-5b96-4981-a0a6-620667353479", "810fa2d0-5b96-4981-a0a6-620667353479"),
    ("810FA2D0-5B96-4981-A0A6-620667353479", "810fa2d0-5b96-4981-a0a6-620667353479"),
    ("marcelo-810fa2d0", "marcelo-810fa2d0"),
    ("2mil-multimarcas-f1c53532", "2mil-multimarcas-f1c53532"),
    ("https://www.olx.com.br/perfil/810fa2d0-5b96-4981-a0a6-620667353479", "810fa2d0-5b96-4981-a0a6-620667353479"),
    ("https://www.olx.com.br/perfil/marcelo-810fa2d0?origin=menu", "marcelo-810fa2d0"),
    ("https://avaliacoes.olx.com.br/vendedor/94389f77-e329-42a0-af2a-b6e1b86e81aa", "94389f77-e329-42a0-af2a-b6e1b86e81aa"),
])
def test_resolve_seller(value, expected):
    assert refs.resolve_seller(value) == expected


@pytest.mark.parametrize("value", ["", "173778320", "marcelo", "https://example.com/perfil/x",
                                   "https://www.olx.com.br/vi/1542267399"])
def test_resolve_seller_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_seller(value)


@pytest.mark.parametrize("value,expected", [
    ("celulares", "celulares"),
    ("/Autos-e-Pecas/Carros-Vans-e-Utilitarios/", "autos-e-pecas/carros-vans-e-utilitarios"),
    ("3060", "3060"),
    ("https://www.olx.com.br/imoveis/venda/casas/estado-rj", "imoveis/venda/casas"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


@pytest.mark.parametrize("value", ["", "estado-sp", "cel ulares", "12", "https://example.com/celulares"])
def test_resolve_category_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_category(value)


@pytest.mark.parametrize("value,expected", [
    ("sp", {"path": "estado-sp"}),
    ("RJ", {"path": "estado-rj"}),
    ("estado-sp/sao-paulo-e-regiao/zona-oeste", {"path": "estado-sp/sao-paulo-e-regiao/zona-oeste"}),
    ("zone-2143", {"filter": ["zone", "2143"]}),
    ("sd_id-nb18278", {"filter": ["sd_id", "nb18278"]}),
    ("Region-11", {"filter": ["region", "11"]}),
    ("https://www.olx.com.br/celulares/estado-rj/rio-de-janeiro-e-regiao", {"path": "estado-rj/rio-de-janeiro-e-regiao"}),
])
def test_resolve_location(value, expected):
    assert refs.resolve_location(value) == expected


@pytest.mark.parametrize("value", ["", "xx", "estado-xx", "campinas", "https://www.olx.com.br/celulares"])
def test_resolve_location_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_location(value)


def test_resolve_fipe_brand():
    assert refs.resolve_fipe_brand("Fiat") == "fiat"
    assert refs.resolve_fipe_brand("https://www.olx.com.br/tabela-fipe/carros/gm-chevrolet") == "gm-chevrolet"
    with pytest.raises(ValueError):
        refs.resolve_fipe_brand("https://www.olx.com.br/tabela-fipe/carros")
    with pytest.raises(ValueError):
        refs.resolve_fipe_brand("fi at")


# ---- value helpers ----------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("R$ 2.200", 2200.0), ("R$ 1.234,56", 1234.56), ("R$ 1", 1.0), ("R$ 119.990", 119990.0),
    ("Não informado", None), ("", None), (None, None),
])
def test_parse_price(value, expected):
    assert P.parse_price(value) == expected


def test_price_block():
    assert P.price_block("R$ 2.200", None) == {"amount": 2200.0, "currency": "BRL", "text": "R$ 2.200", "old_amount": None}
    assert P.price_block(None, None) is None
    assert P.price_block("", "R$ 10")["old_amount"] == 10.0


def test_dates():
    assert P.epoch_iso(1792708535) == "2026-10-22T22:35:35Z"
    assert P.epoch_iso(0) is None
    assert P.utc_iso("2026-10-22T22:35:35.000Z") == "2026-10-22T22:35:35Z"
    assert P.sao_paulo_iso("2026-10-22 19:35:35") == "2026-10-22T22:35:35Z"
    assert P.local_iso("2025-08-19T15:45:54.82455") == "2025-08-19T15:45:54"
    assert P.utc_iso("garbage") is None


def test_text_helpers():
    assert P.strip_tags("<b>IPHONE</b> <b>13</b>") == "IPHONE 13"
    assert P.text_with_breaks("a<br>b<br/> c &amp; d") == "a\nb\nc & d"
    assert P._int(0) == 0 and P._int(False) is None and P._int("12") == 12
    assert P._unquote_config('"AUTOS"') == "AUTOS" and P._unquote_config("[]") == []


# ---- listing pages -------------------------------------------------------------------------

def test_listing_phones(phones):
    assert phones["total_count"] == 97239
    assert phones["page"] == 1 and phones["page_size"] == 50
    assert len(phones["results"]) == 50          # the 7 featured slots without a listId are dropped
    assert phones["query"] == "iphone"
    assert phones["category"] == {"code": 3060, "name": "Celulares e Smartphones",
                                  "path": "celulares", "parent_code": 3000}
    assert phones["location"] is None
    assert phones["applied_filters"] == {"sort": "relevance", "keyword": "iphone", "selectedCategoryCode": "3060"}
    first = phones["results"][0]
    assert first["id"] == 1542267399
    assert first["title"] == "iPhone 15 no preçinho"
    assert first["link"].endswith("-1542267399")
    assert first["price"] == {"amount": 2200.0, "currency": "BRL", "text": "R$ 2.200", "old_amount": None}
    assert first["posted_at"] == "2026-10-22T22:35:35Z"
    assert first["location"] == {"text": "Rio de Janeiro, Padre Miguel", "municipality": "Rio de Janeiro",
                                 "neighbourhood": "Padre Miguel", "state": "RJ", "ddd": "21"}
    assert first["images"][0].startswith("https://img.olx.com.br/images/")
    assert first["image_count"] == 2
    assert {a["name"]: a["value"] for a in first["attributes"]}["electronics_model"] == "IPHONE 15"
    assert first["is_professional"] is False and first["is_featured"] is False
    assert first["olx_pay"]["is_enabled"] is True
    assert first["olx_pay"]["max_installments"] == 10
    assert "Frete grátis" in first["olx_pay"]["badges"]
    assert first["has_delivery"] is True
    assert first["vehicle"] is None
    assert all(r["id"] for r in phones["results"])


def test_listing_filters_template(phones, cars):
    filters = P.parse_filters_template(phones["filters_template"])
    names = {f["name"]: f for f in filters}
    assert names["price"]["query_keys"] == ["ps", "pe"]
    assert names["electronics_brand"]["values_link"].endswith("/attributes/cellphone_brand")
    assert names["electronics_condition"]["values"][0] == {"value": "1", "label": "Novo"}
    assert names["sort"]["values"][1] == {"value": "date", "label": "Mais Recentes"}
    car_filters = {f["name"]: f for f in P.parse_filters_template(cars["filters_template"])}
    assert car_filters["regdate"]["query_keys"] == ["rs", "re"]
    assert car_filters["fuel"]["values"][2] == {"value": "3", "label": "Flex"}
    assert "brands" not in car_filters                      # template items without props are skipped


def test_listing_cars(cars):
    assert cars["category"]["path"] == "autos-e-pecas/carros-vans-e-utilitarios"
    assert cars["location"] == {"id": "state-1", "name": "São Paulo", "description": "São Paulo",
                                "path": "/estado-sp", "state": "SP"}
    assert cars["breadcrumbs"][-1] == {"label": "SP", "path": "/autos-e-pecas/carros-vans-e-utilitarios/estado-sp"}
    assert cars["listing_path"] == "/autos-e-pecas/carros-vans-e-utilitarios/estado-sp"
    first = cars["results"][0]
    assert first["price"]["old_amount"] == 124990.0 and first["has_price_reduction"] is True
    assert first["is_professional"] is True and first["is_featured"] is True
    assert first["vehicle"] == {"tags": ["Aceita troca", "IPVA pago", "Único dono"], "has_inspection_report": False}
    assert first["seller_google_rating"] == 2.4
    assert first["category"] == {"name": "Carros, vans e utilitários", "search_category_code": 2020}


def test_listing_houses(houses):
    first = houses["results"][0]
    assert first["category"] == {"name": "Casas", "search_category_code": 1001}
    attrs = {a["name"]: a["value"] for a in first["attributes"]}
    assert attrs["rooms"] == "4" and attrs["size"] == "200m²"
    assert houses["total_count"] == 455805


def test_listing_empty():
    empty = P.parse_listing(fixture("listing_empty.html"))
    assert empty["results"] == []
    assert empty["total_count"] == 0
    assert empty["page"] == 1
    assert empty["query"] == "xqzvbnwklp"
    assert empty["category"] is None


def test_home_fallback_is_not_a_listing():
    html = fixture("home_fallback_unknown_category.html")
    assert '"pageType":"listing"' not in html and '"topazioQuery"' not in html
    assert P.parse_listing(html)["results"] == []


# ---- ad pages -------------------------------------------------------------------------------

def test_ad_phone():
    ad = P.parse_ad(fixture("ad_phone.html"), 1542267399)
    assert ad["id"] == 1542267399 and ad["ad_id"] == 1816265350
    assert ad["title"] == "iPhone 15 no preçinho"
    assert ad["description"] == "iPhone 15 super novo tudo original nunca foi aberto"
    assert ad["price"]["amount"] == 2200.0 and ad["is_price_shown"] is True
    assert ad["category"] == {"code": 3060, "name": "Celulares e Smartphones", "parent_code": 3000,
                              "parent_name": "Celulares e Telefonia"}
    assert ad["posted_at"] == "2026-10-22T22:35:35Z"
    assert ad["location"]["zipcode"] == "21775040" and ad["location"]["zone"] == "zona-oeste"
    assert ad["location"]["latitude"] is None            # the site prints 0 when it has no pin
    assert ad["seller"]["public_id"] == "810fa2d0-5b96-4981-a0a6-620667353479"
    assert ad["seller"]["link"] == "https://www.olx.com.br/perfil/810fa2d0-5b96-4981-a0a6-620667353479"
    assert ad["seller"]["is_professional"] is False
    assert ad["phone"] == {"masked": None, "is_hidden": True, "is_verified": True, "exists": False}
    assert len(ad["images"]) == 2 and ad["images"][0]["thumbnail_link"].startswith("https://img.olx.com.br/thumbs100x100/")
    assert ad["olx_pay"]["installments"][-1] == {"times": 10, "amount": 220.0, "fee": 0.0, "is_highlighted": True}
    assert ad["olx_pay"]["payment_discount"]["method"] == "PIX"
    assert ad["delivery"] == {"is_enabled": True, "weight": 1.0, "is_seller_paying_shipping": True}
    assert ad["vehicle"] is None and ad["real_estate"] is None
    assert ad["breadcrumbs"][0] == {"label": "Rio de Janeiro", "link": "https://www.olx.com.br/estado-rj"}


def test_ad_car(car_ad):
    ad = car_ad
    assert ad["price"] == {"amount": 119990.0, "currency": "BRL", "text": "R$ 119.990", "old_amount": 124990.0}
    assert "\n" in ad["description"]                       # <br> kept as line breaks
    assert ad["seller"]["name"] == "2Mil Multimarcas"
    assert ad["seller"]["is_professional"] is True and ad["seller"]["pro_vertical"] == "AUTOS"
    assert ad["seller"]["is_cnpj_verified"] is True and ad["seller"]["has_whatsapp"] is True
    assert ad["phone"]["masked"] == "1194007*..." and ad["phone"]["is_hidden"] is False
    vehicle = ad["vehicle"]
    assert vehicle["fipe_price"] == 113653.0
    assert vehicle["market_price"]["median"] == 116990.0 and vehicle["market_price"]["sample_size"] == 30
    assert vehicle["financing"] == {"installment": "48x R$ 3.176,78*", "down_payment": "R$ 26.397,80"}
    assert vehicle["tags"] == ["Aceita troca", "IPVA pago", "Único dono"]
    assert vehicle["codes"] == {"vehicle_brand": "7", "vehicle_model": "35", "vehicle_version": "7"}
    assert "Laudo cautelar" in vehicle["seller_differentials"]
    assert len(ad["attributes"]) == 37
    assert ad["attributes"][0]["link"].startswith("https://www.olx.com.br/autos-e-pecas/")
    assert len(ad["images"]) == 20


def test_ad_house():
    ad = P.parse_ad(fixture("ad_house.html"))
    assert ad["id"] == 1546832349
    assert ad["category"]["code"] == 1040 and ad["category"]["parent_name"] == "Imóveis"
    assert ad["location"]["latitude"] == -21.78169 and ad["location"]["longitude"] == -41.319835
    estate = ad["real_estate"]
    assert estate["zap_listing_id"] == "2918948048" and estate["is_zap_bundle"] is True
    assert estate["price_info"][0] == {"name": "Preço", "label": "Venda", "value": "R$ 457.300",
                                       "amount": 457300.0, "period": None}
    assert estate["price_info"][1]["amount"] is None        # "Não informado" -> null
    assert ad["seller"]["pro_vertical"] == "REALESTATE"
    assert ad["vehicle"] is None


def test_ad_removed_page_is_not_an_ad():
    assert P.parse_ad(fixture("ad_removed_410.html"), 1) is None
    assert P.parse_ad("<html></html>") is None


def test_ad_video_slides_go_to_videos():
    """An ad with a video lists it twice: as a gallery slide without an
    `original` (its YouTube thumbnail only) and in `videos` (shape seen on
    ad 1520987141, 2026-10-26)."""
    import html as html_lib
    blob = {"ad": {"adId": 1794988720, "listId": 1520987141, "subject": "Porsche 911 4 GTS Targa",
                   "images": [{"original": "https://img.olx.com.br/images/30/306631688270333.jpg",
                               "thumbnail": "https://img.olx.com.br/thumbs100x100/30/306631688270333.jpg"},
                              {"original": None, "thumbnail": "https://img.youtube.com/vi/qvDLebdFkLc/mqdefault.jpg"}],
                   "videos": [{"url": "https://www.youtube.com/watch?v=qvDLebdFkLc",
                               "thumbnail": "https://img.youtube.com/vi/qvDLebdFkLc/mqdefault.jpg"},
                              {"url": None}]}}
    page = ('<script id="initial-data" type="text/plain" data-json="'
            + html_lib.escape(json.dumps(blob)) + '"></script>')
    ad = P.parse_ad(page)
    assert [i["link"] for i in ad["images"]] == ["https://img.olx.com.br/images/30/306631688270333.jpg"]
    assert ad["videos"] == [{"link": "https://www.youtube.com/watch?v=qvDLebdFkLc",
                             "thumbnail_link": "https://img.youtube.com/vi/qvDLebdFkLc/mqdefault.jpg"}]


# ---- profiles -----------------------------------------------------------------------------

def test_profile_private():
    profile = P.parse_profile(fixture("profile_private.html"))
    seller = profile["seller"]
    assert seller["id"] == 157017627
    assert seller["public_id"] == "810fa2d0-5b96-4981-a0a6-620667353479"
    assert seller["slug"] == "marcelo-810fa2d0" and seller["name"] == "Marcelo"
    assert seller["member_since"] == "2026-09-10T18:55:38Z"
    assert seller["verifications"] == {"phone": True, "email": True, "facebook": False, "identity": True}
    assert seller["location"] == {"state": "RJ", "city": "Rio de Janeiro", "neighbourhood": "Padre Miguel"}
    assert seller["chat_response_time"] == "2h" and seller["is_professional"] is False
    assert profile["history"]["published_ads_count"] == 4
    assert profile["ratings"] == {"average": 0.0, "count": 0, "reviews": []}
    assert profile["ads"]["total_count"] == 4 and len(profile["ads"]["results"]) == 4
    first = profile["ads"]["results"][0]
    assert first["id"] == 1542267399 and first["posted_at"] == "2026-10-22T22:35:35Z"   # BRT shifted to UTC
    assert first["images"] == ["https://img.olx.com.br/images/70/700665213820829.jpg",
                               "https://img.olx.com.br/images/71/719664339764396.jpg"]
    assert first["location"]["state_id"] == 3
    assert profile["token"]


def test_profile_pro():
    profile = P.parse_profile(fixture("profile_pro.html"))
    seller = profile["seller"]
    assert seller["is_professional"] is True and seller["pro_vertical"] == "AUTOS" and seller["profile_type"] == "pro"
    assert seller["is_key_account"] is True and seller["is_cnpj_verified"] is True
    assert seller["google_reviews"] == {"status": "confirmed", "is_visible": True}
    assert seller["is_online"] is True and seller["score"] == "ADVANCED"
    assert profile["history"]["ads_last_90_days_count"] == 77
    assert profile["ads"]["total_count"] == 21 and len(profile["ads"]["results"]) == 12
    assert profile["ads"]["categories"] == [{"code": 2020, "name": "Carros, vans e utilitários"}]


def test_profile_rated():
    profile = P.parse_profile(fixture("profile_rated.html"))
    assert profile["ratings"]["average"] == 5.0 and profile["ratings"]["count"] == 2
    review = profile["ratings"]["reviews"][0]
    assert review["comment"] == "Hiper atenciosa e cuidadosa no envio"
    assert review["reviewer"]["first_name"] == "Edinelma"
    assert review["evaluated_at"] == "2025-08-19T15:45:54"
    assert profile["history"]["sales_count"] == 2 and profile["history"]["shipped_sales_count"] == 1


def test_profile_not_found_page():
    assert P.parse_profile(fixture("profile_not_found.html")) is None


def test_seller_ads_page():
    page = P.parse_seller_ads(fixture("seller_ads_page.json"))
    assert page["total_count"] == 20 and len(page["results"]) == 20
    first = page["results"][0]
    assert first["id"] == 1546928006
    assert first["price"]["amount"] == 76890.0
    assert first["posted_at"] == "2026-10-23T17:39:31Z"
    assert first["description"] == "-Laudo Cautelar Aprovado\n-Troco E Financio Sem Entrada"
    assert first["is_professional"] is True and first["image_count"] == 15
    assert page["categories"] == [{"code": 2020, "name": "Carros, vans e utilitários"}]
    assert page["states"] == [{"id": 1, "name": "São Paulo"}]
    empty = P.parse_seller_ads(fixture("seller_ads_empty.json"))
    assert empty == {"total_count": 0, "results": [], "categories": [], "states": []}
    assert P.parse_seller_ads(None)["results"] == []


# ---- reviews -----------------------------------------------------------------------------

def test_reviews_rated():
    reviews = P.parse_reviews(fixture("reviews_rated.html"))
    assert reviews["seller_id"] == "97781590" and reviews["count"] == 2 and reviews["average"] == 5.0
    first = reviews["reviews"][0]
    assert first["id"] == "b9f60524-13c4-4204-b609-dd8dff49cd9d"
    assert first["score"] == 5.0 and first["product_name"] == "iPhone 12 Preto 64gb com Cabo Lightning"
    assert first["reviewer"] == {"first_name": "Edinelma", "last_name": None, "account_id": 113418818,
                                 "member_since": "Na OLX desde de janeiro de 2022", "profile_link": None}


def test_reviews_empty():
    reviews = P.parse_reviews(fixture("reviews_empty.html"))
    assert reviews == {"seller_id": "104709715", "average": None, "count": 0, "reviews": []}
    assert P.parse_reviews("<html></html>") is None


# ---- suggestions / locations / attributes --------------------------------------------------

def test_suggestions():
    results = P.parse_suggestions(fixture("suggestions_iphone13.json"))
    assert results[0] == {"text": "iphone 13", "description": "em Todas as categorias", "category": None,
                          "filters": {"q": "iphone 13"}, "probability": 0.0}
    assert results[1]["text"] == "IPHONE 13"
    assert results[1]["category"] == {"code": 3060, "name": "Celulares e Smartphones"}
    assert results[1]["filters"] == {"search_category": "3060", "electronics_brand": "2", "electronics_model": "8"}
    empty = P.parse_suggestions(fixture("suggestions_empty.json"))
    assert len(empty) == 1 and empty[0]["category"] is None
    assert P.parse_suggestions(None) == [] and P.parse_suggestions([]) == []


def test_locations():
    results = P.parse_locations(fixture("locations_campinas.json"))
    assert results[0] == {"id": "zone-sd3460", "name": "Campinas", "description": "Em DDD 19 - Grande Campinas",
                          "path": "estado-sp/grande-campinas/campinas", "state": "SP",
                          "filter": {"key": "zone", "value": "sd3460"}}
    assert results[1]["filter"] == {"key": "sd_id", "value": "nb18278"}
    assert P.parse_locations(fixture("locations_empty.json")) == []
    # every id round-trips into a search `location`
    for item in results:
        assert refs.resolve_location(item["id"])["filter"] == [item["filter"]["key"], item["filter"]["value"]]


def test_attribute_values():
    brands = P.parse_attribute_values(fixture("attributes_cellphone_brand.json"))
    assert brands[0] == {"value": "2", "label": "APPLE", "path": "apple"}
    assert len(P.parse_attribute_values(fixture("attributes_cellphone_model_apple.json"))) == 45


def test_generate_url_fixture_shape():
    assert fixture("generate_url_zone.json") == {"url": "/celulares/estado-rj/rio-de-janeiro-e-regiao/zona-oeste"}


# ---- categories ----------------------------------------------------------------------------

def test_categories_tree():
    tree = P.parse_categories(fixture("sitemap.html"), fixture("home.html"))
    by_path = {node["path"]: node for node in tree}
    assert "autos-e-pecas" in by_path and "imoveis" in by_path and "celulares" in by_path
    autos = {c["path"] for c in by_path["autos-e-pecas"]["children"]}
    assert {"autos-e-pecas/carros-vans-e-utilitarios", "autos-e-pecas/motos", "autos-e-pecas/caminhoes"} <= autos
    imoveis = {c["path"]: c for c in by_path["imoveis"]["children"]}
    assert "imoveis/aluguel" in imoveis and "imoveis/venda" in imoveis
    assert {g["path"] for g in imoveis["imoveis/aluguel"]["children"]} >= {"imoveis/aluguel/apartamentos",
                                                                           "imoveis/aluguel/casas"}
    assert by_path["imoveis"]["link"] == "https://www.olx.com.br/imoveis"
    assert all(node["name"] for node in tree)
    assert "brasil" not in by_path and "mapa-do-site" not in by_path


def test_categories_sitemap_only():
    tree = P.parse_categories(fixture("sitemap.html"))
    assert len(tree) > 30


# ---- FIPE -----------------------------------------------------------------------------------

def test_fipe_brands():
    cars = P.parse_fipe(fixture("fipe_cars.html"))
    assert cars["vehicle_type"] == "carros" and len(cars["brands"]) == 107
    assert cars["brands"][0] == {
        "id": 116, "name": "Chevrolet", "slug": "gm-chevrolet",
        "link": "https://www.olx.com.br/tabela-fipe/carros/gm-chevrolet", "legacy_code": 29,
        "legacy_code_motorcycle": None, "has_car": True, "has_motorcycle": False, "has_truck": False,
        "logo_link": "https://cdn-autos-aqui.olx.com.br/brand-logos/car/gm-chevrolet-60_60.png"}
    motos = P.parse_fipe(fixture("fipe_motos.html"))
    assert motos["vehicle_type"] == "motos" and motos["brands"][0]["legacy_code_motorcycle"] == 15


def test_fipe_models():
    fiat = P.parse_fipe(fixture("fipe_cars_fiat.html"))
    assert fiat["brand"] == {"name": "Fiat", "slug": "fiat", "legacy_code": 25, "legacy_code_motorcycle": None,
                             "logo_link": "https://cdn-autos-aqui.olx.com.br/brand-logos/fiat.png"}
    assert len(fiat["models"]) == 40
    assert fiat["models"][0] == {"name": "Uno", "slug": "uno", "vehicle_type": "CARRO", "legacy_code": 27,
                                 "link": "https://www.olx.com.br/tabela-fipe/carros/fiat/uno"}


def test_fipe_unknown_brand_page():
    assert P.parse_fipe(fixture("fipe_unknown_brand_404.html")) is None
