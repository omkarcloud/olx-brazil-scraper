"""Cache TTL per /olx-brazil/* endpoint (cache.py, keyed on the validated
params). Classifieds move fast: new ads land every minute and sellers
bump / remove them, so search and seller-ad pages are cached briefly; one
ad's own page and a seller's profile change rarely once published; the
site's taxonomy (categories, filter lists, locations, FIPE tables) is
practically static.
"""
from datetime import timedelta

# Listing pages reorder as ads are posted and bumped.
SEARCH_CACHE = timedelta(minutes=15)
# One ad's page: price edits and removals are the only moves.
AD_CACHE = timedelta(hours=6)
# Seller profile (verifications, counts, first ads).
PROFILE_CACHE = timedelta(hours=6)
# A seller's ad list page (the profile BFF).
SELLER_ADS_CACHE = timedelta(hours=1)
# Ratings land after a sale is confirmed, days apart.
REVIEWS_CACHE = timedelta(hours=12)
# Search-box suggestions are a slow-moving model.
SUGGEST_CACHE = timedelta(hours=24)
# Location / category / filter / FIPE taxonomies.
LOCATIONS_CACHE = timedelta(days=7)
CATEGORIES_CACHE = timedelta(days=7)
FILTERS_CACHE = timedelta(days=7)
FIPE_CACHE = timedelta(days=7)
# The url-parser's friendly path for a filter set (category code / location id).
URL_CACHE = timedelta(days=7)
