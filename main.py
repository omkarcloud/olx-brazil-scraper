"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The functions take the values the API's params resolve to:
an ad ID as an int, a seller's public ID, a category path.
"""
import json
import os

from olx_brazil.api import ad_details, ads_search, seller_details

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # one full ad: price, photos, specs, seller, FIPE value
    save("ad_1520987141.json", ad_details(1520987141))

    # 50 ads per page, any keyword / category / location / filters
    save("search_porsche_911.json", ads_search(query="porsche 911",
                                               category="autos-e-pecas/carros-vans-e-utilitarios", page=1))

    # a seller's profile, ratings and recent ads
    save("seller_afan_multimarcas.json", seller_details("02f2d673-f90b-4977-9abd-16cdd5920152"))
