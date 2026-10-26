"""Marshmallow request schemas for every /olx-brazil/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair; olx_brazil/refs.py resolves each):

    ad         the ad id (the number ending every ad link) OR the ad link
    seller     the seller's public id (UUID), profile slug (name-xxxxxxxx)
               OR the profile link
    category   a category path ("celulares", "autos-e-pecas/carros-vans-e-
               utilitarios") OR a category code (3060) OR a category link
    location   a state code ("sp"), a location path ("estado-sp/sao-paulo-e-
               regiao/zona-oeste") OR a location id from /locations/search
               ("zone-2143", "region-11", "state-1", "sd_id-nb18278")
    brand      a FIPE brand slug ("fiat") OR its /tabela-fipe link

Every field carries a one-line `description`: it becomes the public docs.
"""
import re

from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import (BaseSchema, ChoiceField, PageField, PositiveInt, Price, QueryField,
                           RefField, StrippedString)
from olx_brazil import refs

MAX_SEARCH_PAGE = 100     # the site serves page 100 for anything higher
SEARCH_PAGE_SIZE = 50     # the listing page's own size (plus featured slots we drop)
SELLER_ADS_PAGE_SIZE = 50  # the profile BFF's largest accepted `limit`
MAX_BATCH = 10

_FILTER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_FILTER_VALUE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


def _max_length(n):
    """Length(max=n) that tolerates the None an optional StrippedString
    yields for an empty value (QueryField's own Length(min=1) would raise
    TypeError on `?query=`)."""
    return lambda value: value is None or bool(validate.Length(max=n)(value))


class AdRefField(RefField):
    resolver = staticmethod(refs.resolve_ad)


class SellerRefField(RefField):
    resolver = staticmethod(refs.resolve_seller)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class LocationRefField(RefField):
    resolver = staticmethod(refs.resolve_location)


class FipeBrandRefField(RefField):
    resolver = staticmethod(refs.resolve_fipe_brand)


class AdListField(fields.Field):
    """Comma-separated ad ids and/or ad links -> [int, ...] (deduped)."""

    def __init__(self, max_items=MAX_BATCH, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)
        self.max_items = max_items

    def _deserialize(self, value, attr, data, **kwargs):
        ids = []
        for raw in str(value).split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                list_id = refs.resolve_ad(raw)
            except ValueError as e:
                raise ValidationError(f"'{raw}': {e}")
            if list_id not in ids:
                ids.append(list_id)
        if not ids:
            raise ValidationError("Must not be empty.")
        if len(ids) > self.max_items:
            raise ValidationError(f"At most {self.max_items} ads per call.")
        return ids


class ExtraFiltersField(StrippedString):
    """Raw site filters as "key=value,key=value" (the `query_keys` and
    `values` from /olx-brazil/categories/filters, e.g. "gb=2,fu=3,cf=5")."""

    def __init__(self, max_items=15, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)
        self.max_items = max_items

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        out = {}
        for pair in value.split(","):
            pair = pair.strip()
            if not pair:
                continue
            key, sep, val = pair.partition("=")
            key, val = key.strip().lower(), val.strip()
            if not sep or not _FILTER_KEY_RE.match(key) or not _FILTER_VALUE_RE.match(val):
                raise ValidationError(f"'{pair}' is not key=value (letters, digits, _ . -).")
            out[key] = val
        if len(out) > self.max_items:
            raise ValidationError(f"At most {self.max_items} filters.")
        return out or None


def _non_negative_int(max_value, description):
    return fields.Integer(load_default=None, strict=False,
                          validate=validate.Range(min=0, max=max_value),
                          metadata={"description": description})


class AdsSearchSchema(BaseSchema):
    query = QueryField(required=False, load_default=None, validate=_max_length(200), metadata={
        "description": "keyword to search for (optional when a category or location is given)"})
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "category path (celulares, autos-e-pecas/carros-vans-e-utilitarios, "
                       "imoveis/venda) or code (3060) from /olx-brazil/categories/list, or a category link"})
    location = LocationRefField(required=False, load_default=None, metadata={
        "description": "state code (sp), location path (estado-sp/sao-paulo-e-regiao) or a "
                       "location id from /olx-brazil/locations/search (zone-2143, region-11)"})
    sort = ChoiceField(list(refs.SORT_QUERY), load_default="relevance", metadata={
        "description": "relevance (default), newest or lowest_price"})
    seller_type = ChoiceField(refs.SELLER_TYPE, metadata={
        "description": "private or professional sellers only"})
    condition = ChoiceField(refs.CONDITION, metadata={
        "description": "new, used_excellent, used_good, refurbished or defective (electronics)"})
    price_min = Price(metadata={"description": "minimum price in BRL"})
    price_max = Price(metadata={"description": "maximum price in BRL"})
    year_min = PositiveInt(max_value=2100, metadata={"description": "vehicles: earliest model year"})
    year_max = PositiveInt(max_value=2100, metadata={"description": "vehicles: latest model year"})
    mileage_min = _non_negative_int(5_000_000, "vehicles: minimum mileage in km")
    mileage_max = _non_negative_int(5_000_000, "vehicles: maximum mileage in km")
    gearbox = ChoiceField(refs.GEARBOX, metadata={
        "description": "vehicles: manual, automatic, semi_automatic or automated"})
    fuel = ChoiceField(refs.FUEL, metadata={
        "description": "vehicles: gasoline, ethanol, flex, diesel, hybrid or electric"})
    rooms = _non_negative_int(5, "real estate: number of bedrooms (5 = five or more)")
    bathrooms = _non_negative_int(5, "real estate: number of bathrooms (5 = five or more)")
    garage_spaces = _non_negative_int(5, "real estate: parking spaces (5 = five or more)")
    size_min = _non_negative_int(1_000_000, "real estate: minimum area in m²")
    size_max = _non_negative_int(1_000_000, "real estate: maximum area in m²")
    filters = ExtraFiltersField(metadata={
        "description": "extra site filters as key=value pairs from /olx-brazil/categories/filters "
                       "(e.g. gb=2,fu=3 or cpb=2)"})
    page = PageField(max_page=MAX_SEARCH_PAGE, metadata={
        "description": "result page, 50 ads each (the site stops at page 100)"})

    @validates_schema
    def _ranges(self, data, **kwargs):
        for low, high in (("price_min", "price_max"), ("year_min", "year_max"),
                          ("mileage_min", "mileage_max"), ("size_min", "size_max")):
            if data.get(low) is not None and data.get(high) is not None and data[low] > data[high]:
                raise ValidationError(f"{low} must not exceed {high}.", high)


class AdSchema(BaseSchema):
    ad = AdRefField(metadata={"description": "ad id (e.g. 1542267399) or the olx.com.br ad link"})


class AdsBatchSchema(BaseSchema):
    ads = AdListField(metadata={
        "description": f"comma-separated ad ids and/or ad links, up to {MAX_BATCH}"})


class SellerSchema(BaseSchema):
    seller = SellerRefField(metadata={
        "description": "seller public id (UUID from ads/details), profile slug (marcelo-810fa2d0) "
                       "or the www.olx.com.br/perfil/... link"})


class SellerAdsSchema(SellerSchema):
    query = QueryField(required=False, load_default=None, validate=_max_length(100), metadata={
        "description": "keyword to search within the seller's ads"})
    category = PositiveInt(metadata={
        "description": "category code to keep (from the seller's `categories`)"})
    state = PositiveInt(max_value=27, metadata={
        "description": "state id to keep (from the seller's `states`)"})
    sort = ChoiceField(list(refs.SELLER_ADS_SORT), load_default="newest", metadata={
        "description": "newest (default), lowest_price or highest_price"})
    page = PageField(max_page=200, metadata={"description": "result page, 50 ads each"})


class SearchSuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "partial keyword typed so far"})


class LocationsSearchSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={
        "description": "city, neighbourhood, region or state name"})


class CategoriesListSchema(BaseSchema):
    """No parameters."""


class CategoryFiltersSchema(BaseSchema):
    category = CategoryRefField(metadata={
        "description": "category path (autos-e-pecas/carros-vans-e-utilitarios), code (2020) "
                       "or link whose filter list to return"})


class FipeSchema(BaseSchema):
    vehicle_type = ChoiceField(list(refs.FIPE_VEHICLE_TYPES), load_default="carros", metadata={
        "description": "carros (default) or motos"})
    brand = FipeBrandRefField(required=False, load_default=None, metadata={
        "description": "brand slug (fiat, gm-chevrolet) or its /tabela-fipe link for the model list; "
                       "omit for the brand list"})
