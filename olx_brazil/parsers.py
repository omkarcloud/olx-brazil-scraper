"""HTML / JSON -> clean dicts for every /olx-brazil/* endpoint. Pure
functions, no I/O.

Where the data sits (research 2026-10-23/24):
  * listing pages   Next.js app-router "flight" payload: the `self.__next_f
                    .push([1,"..."])` chunks concatenated are one JS string
                    whose `"ads":[...]` array (50 ads + featured slots with
                    no listId), pageIndex, totalOfAds, pageSize, pageTitle,
                    listingUrl, selectedCategory, locations, breadcrumbs,
                    filters (applied) and filtersTemplate we cut out with a
                    raw JSON decode at the key.
  * ad pages        `<script id="initial-data" data-json="...">` — an HTML-
                    escaped JSON blob with `ad` (~80 keys) and `urls`.
  * profile pages   Pages-router `__NEXT_DATA__` props.pageProps: seller
                    profile, history, ratings, the first 12 ads.
  * seller ads      the profile BFF JSON {total, content[], categories, states}
  * reviews page    `__NEXT_DATA__` props.pageProps {sellerId, ratings[]}
  * suggestions / locations / attributes / url-parser: plain JSON lists
  * FIPE pages      `__NEXT_DATA__` props.pageProps {brands} | {brand, models}
  * category tree   the /mapa-do-site links + the home page's menu JSON

Value conventions (shared with the other scraper packages):
  * price   {"amount": 2200.0, "currency": "BRL", "text": "R$ 2.200"} — the
            site prints "R$ 1.234,56" (dot thousands, comma decimals)
  * dates   ISO 8601 UTC: the listing `date` is epoch seconds, the ad page's
            listTime is already UTC, the profile BFF prints São Paulo local
            time ("2026-10-23 14:39:31" = UTC-3) and is shifted here
  * keys    snake_case; `link` not `url`; booleans as questions; null for
            masked / missing values (the phone is masked for everyone who is
            not logged in: "1194007*..." -> `phone.masked`, never the number)

Fixtures captured 2026-10-23/24 (olx_brazil/fixtures/): three listing
pages (phones with a keyword, cars in SP, real estate in RJ), an empty
search, three ad pages (phone, car with FIPE data, house with Zap data), a
removed ad (410), a private and a professional profile, the "Ops" profile,
the profile BFF page, a reviews page, suggestions, locations, attribute
values, url-parser answers and the FIPE brand / model pages.
"""
import html as html_lib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from olx_brazil.refs import SITE, profile_link

_DECODER = json.JSONDecoder()
_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
_INITIAL_DATA_RE = re.compile(r'<script id="initial-data"[^>]*data-json="([^"]*)"', re.S)
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_NUMBER_RE = re.compile(r"-?\d[\d.]*(?:,\d+)?")
_SITEMAP_LINK_RE = re.compile(r'<a[^>]+href="(https://www\.olx\.com\.br/[^"#?]*)"[^>]*>(.*?)</a>', re.S)
_MENU_PAIR_RE = re.compile(r'"label":\s*"([^"]+)",\s*(?:"icon":\s*"[^"]*",\s*)?"(?:url|link)":\s*"(https://www\.olx\.com\.br/[^"#?]*)"')
_SAO_PAULO_OFFSET = timedelta(hours=-3)
_NON_CATEGORY_PATHS = {"", "brasil", "faq.htm", "copyright.htm", "mapa-do-site", "perfil", "vi",
                       "tabela-fipe", "servicos", "cupons", "loja"}


# ---- small value helpers ---------------------------------------------------------

def _clean(value):
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    value = " ".join(str(value).split())
    return value or None


def _int(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_price(value):
    """"R$ 2.200" -> 2200.0, "R$ 1.234,56" -> 1234.56, "R$ 1" -> 1.0; missing
    / "Não informado" -> None."""
    value = _clean(value)
    if value is None:
        return None
    match = _NUMBER_RE.search(value)
    if not match:
        return None
    number = match.group(0).replace(".", "").replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def price_block(text, old_text=None):
    """{"amount", "currency", "text", "old_amount"} or None when the ad
    prints no price at all."""
    text = _clean(text)
    old_text = _clean(old_text)
    if text is None and old_text is None:
        return None
    return {
        "amount": parse_price(text),
        "currency": "BRL",
        "text": text,
        "old_amount": parse_price(old_text),
    }


def epoch_iso(value):
    """Epoch seconds -> "2026-10-22T22:35:35Z"."""
    value = _int(value)
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_iso(value):
    """"2026-10-22T22:35:35.000Z" / "2026-09-10T18:55:38.157Z" -> seconds, Z."""
    value = _clean(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sao_paulo_iso(value):
    """"2026-10-23 14:39:31" (the BFF's São Paulo local time) -> UTC ISO."""
    value = _clean(value)
    if not value:
        return None
    try:
        parsed = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return utc_iso(value)
    return (parsed - _SAO_PAULO_OFFSET).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_iso(value):
    """"2025-08-19T15:45:54.82455" (no zone printed) -> trimmed to seconds."""
    value = _clean(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.split(".")[0].replace("Z", "")).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return value


def strip_tags(value):
    value = _clean(_TAG_RE.sub("", _BR_RE.sub("\n", str(value or ""))))
    return html_lib.unescape(value) if value else None


def text_with_breaks(value):
    """Ad bodies carry <br> line breaks: keep them as newlines."""
    if value is None:
        return None
    text = _TAG_RE.sub("", _BR_RE.sub("\n", str(value)))
    text = html_lib.unescape(text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    text = "\n".join(lines).strip()
    return text or None


def _unquote_config(value):
    """user.configs values arrive JSON-encoded inside strings ('"AUTOS"',
    '[]', 'true'); unwrap one level."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ('"', "[", "{") or stripped in ("true", "false", "null"):
            try:
                return json.loads(stripped)
            except ValueError:
                return stripped.strip('"')
    return value


def _bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().strip('"').lower()
        if low in ("true", "1"):
            return True
        if low in ("false", "0"):
            return False
        return None
    return bool(value)


def _attributes(properties):
    out = []
    for prop in properties or []:
        if not isinstance(prop, dict):
            continue
        name = _clean(prop.get("name"))
        if not name or name == "category":
            continue
        values = prop.get("values")
        out.append({
            "name": name,
            "label": _clean(prop.get("label")),
            "value": _clean(prop.get("value")),
            "values": [_clean(v) for v in values] if isinstance(values, list) and values else None,
            "link": _clean(prop.get("url")),
        })
    return out


# ---- payload extraction ----------------------------------------------------------------

def flight_text(html):
    """The concatenated Next.js flight payload of an app-router page."""
    chunks = _FLIGHT_RE.findall(html or "")
    parts = []
    for chunk in chunks:
        try:
            parts.append(json.loads('"' + chunk + '"'))
        except ValueError:
            continue
    return "".join(parts)


def decode_after(text, key, start=0):
    """The JSON value right after `key` ("\"ads\":") in a JS/JSON text, or
    None. `$undefined` / `$L12` style flight references decode to None."""
    i = text.find(key, start)
    if i < 0:
        return None
    try:
        value, _ = _DECODER.raw_decode(text, i + len(key))
    except ValueError:
        return None
    if isinstance(value, str) and value.startswith("$"):
        return None
    return value


def longest_list_after(text, key):
    """The longest list among every occurrence of `key` (the listing's
    `"ads":[` appears once for the results and once, empty, for the
    "topo VIP" slot)."""
    best = []
    for match in re.finditer(re.escape(key), text):
        try:
            value, _ = _DECODER.raw_decode(text, match.end())
        except ValueError:
            continue
        if isinstance(value, list) and len(value) > len(best):
            best = value
    return best


def initial_data(html):
    """The ad page's `initial-data` blob as a dict."""
    match = _INITIAL_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        return json.loads(html_lib.unescape(match.group(1)))
    except ValueError:
        return None


def next_data(html):
    """`__NEXT_DATA__` props.pageProps of a Pages-router page."""
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        return (json.loads(match.group(1)).get("props") or {}).get("pageProps")
    except (ValueError, AttributeError):
        return None


# ---- listing page ------------------------------------------------------------------

def _location_from_card(card):
    details = card.get("locationDetails") if isinstance(card.get("locationDetails"), dict) else {}
    return {
        "text": _clean(card.get("location")),
        "municipality": _clean(details.get("municipality")),
        "neighbourhood": _clean(details.get("neighbourhood")),
        "state": _clean(details.get("uf")),
        "ddd": _clean(details.get("ddd")),
    }


def _olx_pay(pay):
    if not isinstance(pay, dict):
        return None
    installments = [i for i in (pay.get("installments") or []) if isinstance(i, dict)]
    return {
        "is_enabled": _bool(pay.get("enabled")),
        "badges": [_clean(b.get("text")) for b in (pay.get("transactionalBadges") or [])
                   if isinstance(b, dict) and _clean(b.get("text"))],
        "max_installments": max((_int(i.get("times")) or 0 for i in installments), default=None),
        "seller_name": _clean(pay.get("transactionalSellerName")),
        "seller_rating": _float(pay.get("transactionalSellerRating")),
    }


def _enabled(value):
    if isinstance(value, dict):
        return _bool(value.get("enabled"))
    return _bool(value)


def parse_listing_card(card):
    """One ad from a listing page's `ads` array."""
    images = [img.get("original") for img in (card.get("images") or [])
              if isinstance(img, dict) and img.get("original")]
    pills = [_clean(p.get("label")) for p in (card.get("vehiclePills") or []) if isinstance(p, dict)]
    car = card.get("carSpecificData") if isinstance(card.get("carSpecificData"), dict) else {}
    has_vehicle = bool(pills or car or card.get("vehicleHasInspectionReport") is not None
                       and card.get("vehicleTags"))
    view360 = card.get("view360") if isinstance(card.get("view360"), dict) else {}
    return {
        "id": _int(card.get("listId")),
        "title": _clean(card.get("subject")),
        "link": _clean(card.get("url")),
        "price": price_block(card.get("priceValue"), card.get("oldPrice")),
        # the card prints its own category NAME; the only code it carries is
        # the category the listing was searched in (1001 "venda" for a 1040
        # "casa"), so that one is named for what it is
        "category": {
            "name": _clean(card.get("categoryName") or card.get("category")),
            "search_category_code": _int(card.get("listingCategoryId")),
        },
        "location": _location_from_card(card),
        "posted_at": epoch_iso(card.get("date")),
        "last_bump_age_seconds": _int(card.get("lastBumpAgeSecs")),
        "images": images,
        "image_count": _int(card.get("imageCount")) if card.get("imageCount") is not None else len(images),
        "video_count": _int(card.get("videoCount")) or 0,
        "view_360_link": _clean(view360.get("url")),
        "attributes": _attributes(card.get("properties")),
        "is_professional": _bool(card.get("professionalAd")),
        "is_featured": _bool(card.get("isFeatured")),
        "is_fixed_on_top": _bool(card.get("fixedOnTop")),
        "has_price_reduction": _bool(card.get("priceReductionBadge")),
        "is_chat_enabled": _bool(card.get("isChatEnabled")),
        "is_seller_online": _bool(card.get("isOnline")),
        "seller_google_rating": _float(card.get("userGoogleRating")),
        "vehicle": {
            "tags": [p for p in pills if p],
            "has_inspection_report": _bool(card.get("vehicleHasInspectionReport")
                                           if card.get("vehicleHasInspectionReport") is not None
                                           else car.get("hasAutosInspectionReport")),
        } if has_vehicle else None,
        "olx_pay": _olx_pay(card.get("olxPay")),
        "has_delivery": _enabled(card.get("olxDelivery")),
        "position": _int(card.get("position")),
    }


def parse_filters_template(template):
    """The listing page's filtersTemplate -> the public filter list."""
    out = []
    items = template.get("template") if isinstance(template, dict) else template
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        props = item.get("props") if isinstance(item.get("props"), dict) else {}
        name = _clean(props.get("name"))
        if not name:
            continue
        qs = (props.get("queryStrings") or {}).get("values") or []
        datasource = props.get("datasource") if isinstance(props.get("datasource"), dict) else {}
        values = datasource.get("values")
        out.append({
            "id": _clean(item.get("id")),
            "name": name,
            "label": _clean(props.get("label")),
            "description": _clean(props.get("description")),
            "type": _clean(item.get("type")),
            "query_keys": [_clean(q.get("qs")) for q in qs if isinstance(q, dict) and _clean(q.get("qs"))],
            "values": [{"value": _clean(v.get("value")), "label": _clean(v.get("label"))}
                       for v in values if isinstance(v, dict)] if isinstance(values, list) and values else None,
            "values_link": _clean(datasource.get("url")),
        })
    return out


def parse_listing(html):
    """A listing page -> {results, total_count, page, page_size, title,
    listing_path, query, category, location, breadcrumbs, filters,
    filters_template(raw)}."""
    text = flight_text(html)
    cards = [parse_listing_card(c) for c in longest_list_after(text, '"ads":')
             if isinstance(c, dict) and c.get("listId")]
    applied = decode_after(text, '"filters":') or {}
    selected = decode_after(text, '"selectedCategory":') or {}
    locations = decode_after(text, '"locations":')
    location = locations[0] if isinstance(locations, list) and locations and isinstance(locations[0], dict) else {}
    breadcrumbs = decode_after(text, '"breadcrumbs":') or []
    category = {
        "code": _int(selected.get("value")),
        "name": _clean(selected.get("name")),
        "path": _clean(selected.get("friendlyName")),
        "parent_code": _int(selected.get("parent")),
    } if isinstance(selected, dict) and selected else None
    return {
        "query": _clean(applied.get("keyword")) if isinstance(applied, dict) else None,
        "title": _clean(decode_after(text, '"pageTitle":')),
        "listing_path": _clean(decode_after(text, '"listingUrl":')),
        "category": category,
        "location": {
            "id": _clean(location.get("id")),
            "name": _clean(location.get("title")),
            "description": _clean(location.get("subtitle")),
            "path": _clean(location.get("path")),
            "state": _clean(location.get("uf")),
        } if location else None,
        "breadcrumbs": [{"label": _clean(b.get("label")), "path": _clean(b.get("path"))}
                        for b in breadcrumbs if isinstance(b, dict)],
        "applied_filters": {k: v for k, v in applied.items() if k not in ("pageIndex",)} if isinstance(applied, dict) else {},
        "page": _int(decode_after(text, '"pageIndex":')),
        "page_size": _int(decode_after(text, '"pageSize":')),
        "total_count": _int(decode_after(text, '"totalOfAds":')),
        "results": cards,
        "filters_template": decode_after(text, '"filtersTemplate":'),
    }


# ---- ad page -----------------------------------------------------------------------

def _image(img):
    return {
        "link": _clean(img.get("original")),
        "thumbnail_link": _clean(img.get("thumbnail")),
        "webp_link": _clean(img.get("webpFormat")),
        "alt": _clean(img.get("originalAlt")),
    }


def _seller_from_ad(ad):
    user = ad.get("user") if isinstance(ad.get("user"), dict) else {}
    configs = {k: _unquote_config(v) for k, v in (user.get("configs") or {}).items()} \
        if isinstance(user.get("configs"), dict) else {}
    history = ad.get("sellerHistory") if isinstance(ad.get("sellerHistory"), dict) else {}
    activity = ad.get("accountActivityStatus") if isinstance(ad.get("accountActivityStatus"), dict) else {}
    public_id = _clean(user.get("publicAccountId"))
    whatsapp = user.get("whatsapp") if isinstance(user.get("whatsapp"), dict) else {}
    return {
        "id": _int(user.get("userId")),
        "public_id": public_id,
        "name": _clean(user.get("name")),
        "link": profile_link(public_id) if public_id else None,
        "is_professional": _bool(configs.get("proAccount")),
        "pro_vertical": _clean(configs.get("proAccountVertical")) or None,
        "is_key_account": _bool(user.get("keyAccount")),
        "is_good_seller": _bool(configs.get("isGoodSeller")),
        "is_cnpj_verified": _bool(configs.get("cnpjVerified")),
        "has_whatsapp": _bool(configs.get("whatsappEnabled")) if configs.get("whatsappEnabled") is not None
        else _bool(whatsapp.get("enabled")),
        "has_google_reviews": _bool(configs.get("googleReview")),
        "is_online": _bool(activity.get("isOnline")),
        "sales_count": _int(history.get("salesAmounts")),
        "canceled_sales_count": _int(history.get("canceledSalesAmounts")),
        "average_dispatch_time": _clean(history.get("averageDispatchTime")),
    }


def _vehicle_from_ad(ad):
    car = ad.get("carSpecificData") if isinstance(ad.get("carSpecificData"), dict) else None
    autos = ad.get("autosSpecificData") if isinstance(ad.get("autosSpecificData"), dict) else {}
    fipe = ad.get("abuyFipePrice") if isinstance(ad.get("abuyFipePrice"), dict) else {}
    ref = ad.get("abuyPriceRef") if isinstance(ad.get("abuyPriceRef"), dict) else None
    report = ad.get("vehicleReport") if isinstance(ad.get("vehicleReport"), dict) else {}
    codes = ad.get("vehicleSpecificData") if isinstance(ad.get("vehicleSpecificData"), list) else []
    if car is None and not fipe and not ref and not codes:
        return None
    car = car or {}
    financing = (car.get("financing") or autos.get("financing") or {}) if isinstance(car.get("financing") or autos.get("financing") or {}, dict) else {}
    installment = financing.get("installment") if isinstance(financing.get("installment"), dict) else {}
    upfront = financing.get("upfrontPayment") if isinstance(financing.get("upfrontPayment"), dict) else {}
    return {
        "tags": [_clean(t.get("label")) for t in (car.get("tags") or []) if isinstance(t, dict) and _clean(t.get("label"))],
        "has_inspection_report": _bool(car.get("hasAutosInspectionReport")),
        "has_fair_badge": _bool(car.get("hasAutosFairBadge")),
        "is_financeable": _bool(car.get("isFinanceable") if car.get("isFinanceable") is not None
                                else autos.get("isFinanceable")),
        "financing": {
            "installment": _clean(installment.get("value")),
            "down_payment": _clean(upfront.get("value")),
        } if installment or upfront else None,
        "fipe_price": _float(fipe.get("fipePrice")),
        "market_price": {
            "reference_month": _clean(ref.get("year_month_ref")),
            "min": _float(ref.get("price_min")),
            "p25": _float(ref.get("price_p25")),
            "median": _float(ref.get("price_p50")),
            "p75": _float(ref.get("price_p75")),
            "max": _float(ref.get("price_max")),
            "standard_deviation": _float(ref.get("price_stddev")),
            "sample_size": _int(ref.get("vehicle_count")),
        } if ref else None,
        "report": {
            "is_enabled": _bool(report.get("enabled")),
            "title": _clean(report.get("title")),
            "description": _clean(report.get("description")),
            "consulted_at": _clean(report.get("consultedAt")),
            "source": _clean(report.get("source")),
            "link": _clean(report.get("reportLink")),
            "tags": report.get("tags") if isinstance(report.get("tags"), list) else None,
        } if report else None,
        "features_summary": [{"name": _clean(f.get("name")), "label": _clean(f.get("label")), "value": _clean(f.get("value"))}
                             for f in (ad.get("featuresSummary") or []) if isinstance(f, dict)],
        "additional_information": [_clean(i.get("label")) for i in (ad.get("additionalInformation") or [])
                                   if isinstance(i, dict) and _clean(i.get("label"))],
        "seller_differentials": [_clean(i.get("label")) for i in (ad.get("sellersDifferences") or [])
                                 if isinstance(i, dict) and _clean(i.get("label"))],
        "codes": {_clean(c.get("key")): _clean(c.get("value")) for c in codes
                  if isinstance(c, dict) and _clean(c.get("key"))} or None,
    }


def _real_estate_from_ad(ad):
    info = ad.get("realEstatePriceInfo") if isinstance(ad.get("realEstatePriceInfo"), list) else None
    zap_id = _clean(ad.get("zapListingId"))
    if info is None and not zap_id and not ad.get("planBundleZap"):
        return None
    return {
        "price_info": [{"name": _clean(i.get("name")), "label": _clean(i.get("label")),
                        "value": _clean(i.get("value")), "amount": parse_price(i.get("value")),
                        "period": _clean(i.get("period"))}
                       for i in (info or []) if isinstance(i, dict)],
        "zap_listing_id": zap_id,
        "is_zap_bundle": _bool(ad.get("planBundleZap")),
        "has_highlight": _bool(ad.get("hasRealEstateHighlight")),
        "construction_status_calendar": ad.get("constructionStatusCalendar"),
    }


def _olx_pay_from_ad(ad):
    pay = ad.get("olxPay") if isinstance(ad.get("olxPay"), dict) else None
    if pay is None:
        return None
    discount = pay.get("paymentDiscount") if isinstance(pay.get("paymentDiscount"), dict) else None
    coupon = pay.get("coupon") if isinstance(pay.get("coupon"), dict) else None
    return {
        "is_enabled": _bool(pay.get("enabled")),
        "badges": [_clean(b.get("text")) for b in (pay.get("transactionalBadges") or [])
                   if isinstance(b, dict) and _clean(b.get("text"))],
        "installments": [{
            "times": _int(i.get("times")),
            "amount": _float((i.get("price") or {}).get("raw")) / 100 if isinstance(i.get("price"), dict)
            and (i.get("price") or {}).get("raw") is not None else None,
            "fee": _float((i.get("fee") or {}).get("raw")) / 100 if isinstance(i.get("fee"), dict)
            and (i.get("fee") or {}).get("raw") is not None else None,
            "is_highlighted": _bool(i.get("highlighted")),
        } for i in (pay.get("installments") or []) if isinstance(i, dict)],
        "payment_discount": {
            "method": _clean(discount.get("method")),
            "percentage": _float(discount.get("percentage")),
            "discounted_amount": _float(discount.get("discountedAdPriceValue")),
            "label": _clean(discount.get("adPriceLabel")),
        } if discount else None,
        "coupon": coupon or None,
    }


def parse_ad(html, list_id=None):
    """The ad page -> one full record. Returns None when the page carries no
    initial-data blob (not an ad page)."""
    data = initial_data(html)
    if not data or not isinstance(data.get("ad"), dict):
        return None
    ad = data["ad"]
    # the 410 "ad removed" page ships the same blob with only the listId in it
    if not ad.get("adId") and not ad.get("subject"):
        return None
    location = ad.get("location") if isinstance(ad.get("location"), dict) else {}
    phone = ad.get("phone") if isinstance(ad.get("phone"), dict) else {}
    delivery = ad.get("olxDelivery") if isinstance(ad.get("olxDelivery"), dict) else None
    view360 = ad.get("view360") if isinstance(ad.get("view360"), dict) else {}
    lat, lng = _float(location.get("mapLati")), _float(location.get("mapLong"))
    return {
        "id": _int(ad.get("listId")) or _int(list_id),
        "ad_id": _int(ad.get("adId")),
        "title": _clean(ad.get("subject")),
        "link": _clean(ad.get("friendlyUrl") or ad.get("canonicalUrl")),
        "description": text_with_breaks(ad.get("body") or ad.get("description")),
        "price": price_block(ad.get("priceValue") or ad.get("price"), ad.get("oldPrice")),
        "is_price_shown": _bool(ad.get("showPrice")),
        "category": {
            "code": _int(ad.get("category")),
            "name": _clean(ad.get("categoryName")),
            "parent_code": _int(ad.get("searchCategoryLevelZero")),
            "parent_name": _clean(ad.get("parentCategoryName")),
        },
        "posted_at": utc_iso(ad.get("listTime")) or epoch_iso(ad.get("origListTime")),
        # the gallery also lists each video as a slide with no `original`
        # (only its YouTube thumbnail): those belong to `videos`, not `images`
        "images": [_image(i) for i in (ad.get("images") or [])
                   if isinstance(i, dict) and _clean(i.get("original"))],
        "videos": [{"link": _clean(v.get("url")), "thumbnail_link": _clean(v.get("thumbnail"))}
                   for v in (ad.get("videos") or []) if isinstance(v, dict) and _clean(v.get("url"))],
        "view_360_link": _clean(view360.get("url")),
        "location": {
            "address": _clean(location.get("address")),
            "neighbourhood": _clean(location.get("neighbourhood")),
            "municipality": _clean(location.get("municipality")),
            "zone": _clean(location.get("zone")),
            "region": _clean(location.get("region")),
            "state": _clean(location.get("uf")),
            "zipcode": _clean(location.get("zipcode")),
            "ddd": _clean(location.get("ddd")),
            "latitude": lat if lat else None,
            "longitude": lng if lng else None,
        },
        "attributes": _attributes(ad.get("properties")),
        "seller": _seller_from_ad(ad),
        "phone": {
            "masked": _clean(phone.get("maskedPhone")),
            "is_hidden": _bool(phone.get("phoneHidden")),
            "is_verified": _bool(phone.get("phoneVerified")),
            "exists": _bool(phone.get("phoneExist")),
        },
        "is_professional": _bool(ad.get("professionalAd")),
        "is_featured": _bool(ad.get("isFeatured")),
        "is_chat_enabled": _bool(ad.get("chatEnabled")),
        "vehicle": _vehicle_from_ad(ad),
        "real_estate": _real_estate_from_ad(ad),
        "olx_pay": _olx_pay_from_ad(ad),
        "delivery": {
            "is_enabled": _bool(delivery.get("enabled")),
            "weight": _float(delivery.get("weight")),
            "is_seller_paying_shipping": _bool(delivery.get("isSellerPayingForShip")),
        } if delivery else None,
        "breadcrumbs": [{"label": _clean(b.get("label")), "link": _clean(b.get("url"))}
                        for b in (ad.get("breadcrumbUrls") or []) if isinstance(b, dict)],
    }


# ---- seller profile ---------------------------------------------------------------

def _profile_card(item):
    """One ad from the profile page / profile BFF `content` list."""
    images = []
    for img in item.get("imageList") or []:
        if isinstance(img, dict) and img.get("path"):
            base = (img.get("baseUrl") or "https://img.olx.com.br").rstrip("/")
            images.append(f"{base}/images{img['path']}")
    distinct = item.get("location_distinct") if isinstance(item.get("location_distinct"), dict) else {}
    return {
        "id": _int(item.get("listId")),
        "title": _clean(item.get("title")),
        "link": _clean(item.get("link")),
        "description": text_with_breaks(item.get("description")),
        "price": price_block(item.get("price"), item.get("oldPrice")),
        "category": {"code": _int(item.get("categoryId")), "name": _clean(item.get("category"))},
        "location": {
            "text": _clean(item.get("location")),
            "municipality": _clean(distinct.get("municipality")),
            "neighbourhood": _clean(distinct.get("neighbourhood")),
            "state": _clean(distinct.get("uf")),
            "state_id": _int(item.get("state")),
        },
        "posted_at": sao_paulo_iso(item.get("date")),
        "image": _clean(item.get("image")),
        "images": images,
        "image_count": _int(item.get("numberOfImages")) if item.get("numberOfImages") is not None else len(images),
        "attributes": _attributes(item.get("properties")),
        "is_professional": _bool(item.get("pro")),
        "has_olx_pay": _bool(item.get("olxPay")),
        "has_delivery": _bool(item.get("olxDelivery")),
    }


def parse_seller_ads(payload):
    """The profile BFF page -> {total, results, categories, states}."""
    payload = payload if isinstance(payload, dict) else {}
    return {
        "total_count": _int(payload.get("total")),
        "results": [_profile_card(i) for i in (payload.get("content") or []) if isinstance(i, dict)],
        "categories": [{"code": _int(c.get("id")), "name": _clean(c.get("name"))}
                       for c in (payload.get("categories") or []) if isinstance(c, dict)],
        "states": [{"id": _int(s.get("id")), "name": _clean(s.get("name"))}
                   for s in (payload.get("states") or []) if isinstance(s, dict)],
    }


def _profile_rating(item):
    evaluator = item.get("evaluator") if isinstance(item.get("evaluator"), dict) else {}
    return {
        "id": _clean(item.get("id")),
        "score": _float(item.get("score")),
        "comment": _clean(item.get("comment")),
        "product_name": _clean(item.get("productName")),
        "evaluated_at": local_iso(item.get("evaluationDate")),
        "reviewer": {
            "first_name": _clean(evaluator.get("firstName") or item.get("firstName")),
            "last_name": _clean(evaluator.get("lastName")),
            "account_id": _int(evaluator.get("accountId")),
            "member_since": _clean(evaluator.get("onOlxSince") or item.get("onOlxSince")),
            "profile_link": _clean(item.get("profileURL")),
        },
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
    }


def parse_profile(html):
    """The seller profile page -> {seller, ads_summary, history, ratings,
    ads (first page), token}. None when the page is not a profile."""
    props = next_data(html)
    if not isinstance(props, dict) or "sellerProfileData" not in props:
        return None
    data = props.get("sellerProfileData") if isinstance(props.get("sellerProfileData"), dict) else {}
    configs = data.get("configs") if isinstance(data.get("configs"), dict) else {}
    activity = data.get("lastActivity") if isinstance(data.get("lastActivity"), dict) else {}
    zip_location = data.get("locationDataFromZipCode") if isinstance(data.get("locationDataFromZipCode"), dict) else {}
    facematch = data.get("facematch") if isinstance(data.get("facematch"), dict) else {}
    # the seller level: {"value": "ADVANCED", "description": "Avançado"} or null
    score = data.get("score")
    score = score.get("value") if isinstance(score, dict) else score
    history = props.get("sellerAdsHistory") if isinstance(props.get("sellerAdsHistory"), dict) else {}
    ratings = props.get("sellerRatings") if isinstance(props.get("sellerRatings"), dict) else {}
    ads = parse_seller_ads(props.get("ads"))
    public_id = _clean(data.get("publicAccountId") or props.get("sellerPublicId"))
    return {
        "seller": {
            "id": _int(props.get("sellerId") or history.get("id")),
            "public_id": public_id,
            "name": _clean(data.get("nickname")),
            "slug": _clean(data.get("slug")),
            "link": profile_link(public_id) if public_id else None,
            "profile_picture_link": _clean(data.get("profilePictureUrl") or data.get("imageUrl")),
            "is_professional": _bool(data.get("isPro")),
            "pro_vertical": _clean(_unquote_config(configs.get("proAccountVertical"))) or None,
            "profile_type": _clean(_unquote_config(configs.get("profilePageType"))) or None,
            "is_key_account": _bool(data.get("keyAccount")),
            "is_cnpj_verified": _bool(configs.get("cnpjVerified")),
            "has_whatsapp": _bool(configs.get("whatsappEnabled")),
            "google_reviews": {
                "status": _clean(_unquote_config(configs.get("googleReviewsStatus"))) or None,
                "is_visible": _bool(configs.get("googleReviewsVisible")),
            },
            "creci": _clean(data.get("creci")),
            "score": _clean(score),
            "member_since": utc_iso(data.get("creationDate")),
            "is_new_account": _bool(data.get("isNewAccount")),
            "is_online": _bool(activity.get("online")),
            "last_activity_at": utc_iso(activity.get("timestamp")),
            "chat_response_time": _clean(data.get("chatTimeResponse")),
            "verifications": {
                "phone": _bool(data.get("phoneVerified")),
                "email": _bool(data.get("emailVerified")),
                "facebook": _bool(data.get("facebookVerified")),
                "identity": _bool(facematch.get("profileVerified")),
            },
            "location": {
                "state": _clean(zip_location.get("state")),
                "city": _clean(zip_location.get("city")),
                "neighbourhood": _clean(zip_location.get("neighbourhood")),
            },
        },
        "history": {
            "published_ads_count": _int(history.get("publishedAdsCount")),
            "ads_last_90_days_count": _int(history.get("ads90DaysHistoryCount")),
            "sales_count": _int(history.get("salesAmounts")),
            "shipped_sales_count": _int(history.get("salesAmountsShipping")),
            "canceled_sales_count": _int(history.get("canceledSalesAmounts")),
            "average_dispatch_time": _clean(history.get("averageDispatchTime")),
        },
        "ratings": {
            "average": _float(ratings.get("averageRating")),
            "count": _int(ratings.get("totalElements")),
            "reviews": [_profile_rating(r) for r in (ratings.get("ratings") or []) if isinstance(r, dict)],
        },
        "ads": ads,
        "token": _clean(props.get("accessToken")),
    }


def parse_reviews(html):
    """avaliacoes.olx.com.br/vendedor/<id> -> {seller_id, average, reviews}."""
    props = next_data(html)
    if not isinstance(props, dict) or "ratings" not in props:
        return None
    ratings = [r for r in (props.get("ratings") or []) if isinstance(r, dict)]
    # ratingAverage is {"average": 5, "totalRatings": 2, ...} on a rated
    # page and "" on an unrated one
    rating_average = props.get("ratingAverage")
    if isinstance(rating_average, dict):
        rating_average = rating_average.get("average")
    average = _float(rating_average)
    if average is None and ratings:
        scores = [r.get("score") for r in ratings if isinstance(r.get("score"), (int, float))]
        average = round(sum(scores) / len(scores), 2) if scores else None
    return {
        "seller_id": _clean(props.get("sellerId")),
        "average": average,
        "count": len(ratings),
        "reviews": [_profile_rating(r) for r in ratings],
    }


# ---- suggestions / locations / attributes ------------------------------------------------

def parse_suggestions(payload):
    """The search-box suggestion list -> [{text, description, category,
    filters}]; `filters` are the backend filter name/value pairs the
    suggestion stands for (search_category, electronics_brand, ...)."""
    out = []
    for item in (payload or {}).get("suggestions") or [] if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        filters, category = {}, None
        for f in item.get("filters") or []:
            if not isinstance(f, dict) or not f.get("name"):
                continue
            if f["name"] == "search_placeholder":
                continue
            filters[f["name"]] = _clean(f.get("value"))
            if f["name"] == "search_category":
                category = {"code": _int(f.get("value")), "name": _clean(f.get("label"))}
        out.append({
            "text": strip_tags(item.get("title")),
            "description": _clean(item.get("subtitle")),
            "category": category,
            "filters": filters,
            "probability": _float(item.get("probability")),
        })
    return out


def parse_locations(payload):
    """The location autocomplete list -> [{id, name, description, path,
    state, filter}] — `id` is what /olx-brazil/ads/search takes as
    `location`."""
    out = []
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        filters = item.get("filters") if isinstance(item.get("filters"), dict) else {}
        key, value = (next(iter(filters.items())) if filters else (None, None))
        out.append({
            "id": _clean(item.get("id")),
            "name": _clean(item.get("title")),
            "description": _clean(item.get("subtitle")),
            "path": _clean(item.get("path")),
            "state": _clean(item.get("uf")),
            "filter": {"key": key, "value": _clean(value)} if key else None,
        })
    return out


def parse_attribute_values(payload):
    return [{
        "value": _clean(v.get("value")),
        "label": _clean(v.get("label")),
        "path": _clean((v.get("extraData") or {}).get("friendlyPath")) if isinstance(v.get("extraData"), dict) else None,
    } for v in payload or [] if isinstance(v, dict)]


# ---- category tree -----------------------------------------------------------------

def _category_pairs(sitemap_html, home_html):
    pairs = []
    for link, label in _SITEMAP_LINK_RE.findall(sitemap_html or ""):
        pairs.append((strip_tags(label), link))
    # the home menu is JSON inside the flight payload (quotes escaped in the
    # raw HTML), so it is searched after decoding
    menu_text = flight_text(home_html) if home_html else ""
    for label, link in _MENU_PAIR_RE.findall(menu_text):
        pairs.append((html_lib.unescape(label).strip(), link))
    seen, out = set(), []
    for label, link in pairs:
        path = urlparse(link).path.strip("/").lower()
        if not label or not path or path in _NON_CATEGORY_PATHS or path.startswith("estado-"):
            continue
        if "/estado-" in path or path.split("/")[0] in _NON_CATEGORY_PATHS:
            continue
        if path in seen:
            continue
        seen.add(path)
        out.append((label, path))
    return out


def parse_categories(sitemap_html, home_html=None):
    """The site map's category links (+ the home menu) -> a tree of
    {name, path, link, children}, nested by path segment."""
    nodes = {}
    for label, path in _category_pairs(sitemap_html, home_html):
        nodes[path] = {"name": label, "path": path, "link": f"{SITE}/{path}", "children": []}
    roots = []
    for path in sorted(nodes, key=lambda p: (p.count("/"), p)):
        node = nodes[path]
        parent = None
        probe = path
        while "/" in probe:
            probe = probe.rsplit("/", 1)[0]
            if probe in nodes:
                parent = nodes[probe]
                break
        (parent["children"] if parent else roots).append(node)
    return roots


# ---- FIPE --------------------------------------------------------------------------

def parse_fipe(html):
    """/tabela-fipe/<type>[/<brand>] -> {vehicle_type, brands} or
    {vehicle_type, brand, models}; None when the page has no FIPE data."""
    props = next_data(html)
    if not isinstance(props, dict) or not ("brands" in props or "brand" in props):
        return None
    vehicle_type = _clean(props.get("friendlyVehicleType"))
    if isinstance(props.get("brands"), list):
        return {
            "vehicle_type": vehicle_type,
            "brands": [{
                "id": _int(b.get("id")),
                "name": _clean(b.get("brand")),
                "slug": _clean(b.get("friendlyUrl")),
                "link": f"{SITE}/tabela-fipe/{vehicle_type}/{b.get('friendlyUrl')}" if b.get("friendlyUrl") else None,
                "legacy_code": _int(b.get("legacyCode")),
                "legacy_code_motorcycle": _int(b.get("legacyCodeMotorcycle")),
                "has_car": _bool(b.get("hasCar")),
                "has_motorcycle": _bool(b.get("hasMotorcycle")),
                "has_truck": _bool(b.get("hasTruck")),
                "logo_link": _clean(b.get("logoUrl")),
            } for b in props["brands"] if isinstance(b, dict)],
        }
    brand = props.get("brand") if isinstance(props.get("brand"), dict) else {}
    links = {_clean(m.get("label")): _clean(m.get("url")) for m in (props.get("models") or []) if isinstance(m, dict)}
    models = []
    for m in brand.get("models") or []:
        if not isinstance(m, dict):
            continue
        name = _clean(m.get("model"))
        slug = _clean(m.get("friendlyUrl"))
        models.append({
            "name": name,
            "slug": slug,
            "vehicle_type": _clean(m.get("vehicleType")),
            "legacy_code": _int(m.get("legacyCode")),
            "link": links.get(name) or (f"{SITE}/tabela-fipe/{vehicle_type}/{brand.get('friendlyUrl')}/{slug}"
                                        if slug and brand.get("friendlyUrl") else None),
        })
    return {
        "vehicle_type": vehicle_type,
        "brand": {
            "name": _clean(brand.get("brand")),
            "slug": _clean(brand.get("friendlyUrl")),
            "legacy_code": _int(brand.get("legacyCode")),
            "legacy_code_motorcycle": _int(brand.get("legacyCodeMotorcycle")),
            "logo_link": _clean(brand.get("logoUrl")),
        },
        "models": models,
    }
