"""The Accept-Language header the scraper sends. OLX Brazil is a Brazilian
site, so requests announce Brazilian Portuguese first, the way Chrome on a
machine set up in Brazil does."""

BRAZIL = "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"


def accept_language(proxy=None, country=None):
    """Accept-Language for a session (the same value with or without a proxy)."""
    return BRAZIL
