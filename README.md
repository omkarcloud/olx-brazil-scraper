# 🛒 OLX Brazil Scraper

OLX Brazil Scraper is a **free and open-source** scraper that gets you **unlimited** detailed OLX Brazil data for free.

## ✨ What Can I Get?

- 🔍 **Search 13M+ live ads** — filter by keyword, category, city, price, car and property specs
- 🚗 **Full ad details** — price, photos, every spec, CEP, seller, financing & FIPE value
- 🧑‍💼 **Sellers & buyer reviews** — verifications, sales history, every ad & every review
- 🗺️ **240+ categories, filters & locations** — plus the FIPE car & motorcycle table

## 🎥 Example: A Full OLX Brazil Ad

```json
{
  "id": 1520987141,
  "title": "Porsche 911 4 GTS Targa 3.0 24V (991) 2024",
  "link": "https://pr.olx.com.br/regiao-de-curitiba-e-paranagua/autos-e-pecas/carros-vans-e-utilitarios/porsche-911-4-gts-targa-3-0-24v-991-2024-1520987141",
  "description": "Motor 3.0 biturbo - 480cv, câmbio PDK de 8 marchas e tração integral. Pintura exclusiva Crayon, direção assistida Plus, ParkAssist com Surround View...",
  "price": { "amount": 1180000.0, "currency": "BRL", "text": "R$ 1.180.000", "old_amount": null },
  "category": { "code": 2020, "name": "Carros, vans e utilitários", "parent_code": 2000, "parent_name": "Autos" },
  "posted_at": "2026-10-26T08:54:36Z",
  "images": [
    { "link": "https://img.olx.com.br/images/30/306631688270333.jpg", "thumbnail_link": "https://img.olx.com.br/thumbs100x100/30/306631688270333.jpg" }
  ],
  "location": { "neighbourhood": "Seminário", "municipality": "Curitiba", "state": "PR", "zipcode": "80740000", "ddd": "41" },
  "attributes": [
    { "name": "regdate", "label": "Ano", "value": "2024" },
    { "name": "mileage", "label": "Quilometragem", "value": "6288" }
  ],
  "seller": {
    "public_id": "02f2d673-f90b-4977-9abd-16cdd5920152",
    "name": "AFAN Multimarcas",
    "is_professional": true,
    "is_cnpj_verified": true,
    "has_whatsapp": true
  },
  "phone": { "masked": "4133020...", "is_verified": true },
  "vehicle": {
    "is_financeable": true,
    "financing": { "installment": "48x R$ 31.240,90*", "down_payment": "R$ 259.600,00" }
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free OLX Brazil Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/olx-brazil-scraper
cd olx-brazil-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/ads/details?ad=1520987141"
```

```json
{
  "id": 1520987141,
  "title": "Porsche 911 4 GTS Targa 3.0 24V (991) 2024",
  "price": {
    "amount": 1180000.0,
    "currency": "BRL",
    "text": "R$ 1.180.000",
    "old_amount": null
  },
  "posted_at": "2026-10-26T08:54:36Z",
  "location": {
    "neighbourhood": "Seminário",
    "municipality": "Curitiba",
    "state": "PR",
    "zipcode": "80740000"
  },
  "seller": {
    "name": "AFAN Multimarcas",
    "is_professional": true,
    "is_cnpj_verified": true
  }
}
```

All 11 endpoints are now live at `http://localhost:8000`.

Getting `blocked` errors? OLX Brazil's Cloudflare refuses some IP ranges outright. Set `OLX_BRAZIL_PROXY` to a residential proxy (a Brazilian exit works best) and restart.

## 📚 Endpoints

11 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Ad Details | `/ads/details` | Everything about one ad: price, photos, specs, seller, FIPE value |
| Search Ads | `/ads/search` | 50 ads per page; filter by keyword, category, city, price, specs |
| Ad Details Batch | `/ads/details/batch` | Up to 10 full ads in one call |
| Seller Details | `/sellers/details` | Profile, verifications, sales history, ratings and recent ads |
| Seller Ads | `/sellers/ads` | Every ad of one seller, 50 per page |
| Seller Reviews | `/sellers/reviews` | Every buyer review with score, comment and product bought |
| Search Suggestions | `/search/suggestions` | OLX's own typeahead with category, brand and model |
| Location Search | `/locations/search` | States, cities and neighbourhoods, with IDs for search |
| Categories List | `/categories/list` | The full category tree in one call |
| Category Filters | `/categories/filters` | Every filter a category supports, with allowed values |
| FIPE Table | `/vehicles/fipe` | FIPE car and motorcycle brands, or every model of one brand |


## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-olx-brazil-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-olx-brazil-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-olx-brazil-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/ads/details",
    params={"ad": "1520987141"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about OLX Brazil Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20OLX%20Brazil%20Scraper%20API.)

[![Ask Us by Email about OLX Brazil Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20OLX%20Brazil%20Scraper%20API&body=I%20need%20help%20using%20the%20OLX%20Brazil%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/olx-brazil-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/olx-brazil-scraper)
