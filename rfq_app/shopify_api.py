import requests, os, json
from dotenv import load_dotenv

load_dotenv()

SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "").strip()
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()

# Ensure https:// is always included
if SHOPIFY_STORE_URL and not SHOPIFY_STORE_URL.startswith("http"):
    SHOPIFY_STORE_URL = "https://" + SHOPIFY_STORE_URL

headers = {
    "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
    "Content-Type": "application/json"
}

def get_metafield(product_id, key):
    url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/products/{product_id}/metafields.json"
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    for m in res.json().get("metafields", []):
        if m["namespace"] == "rfq" and m["key"] == key:
            return m["value"]   # ✅ always return raw string
    return "[]"

def get_fabrics(product_id):
    return get_metafield(product_id, "fabric_options")

def get_trims(product_id):
    return get_metafield(product_id, "finish_options")

def get_accessories(product_id):
    return get_metafield(product_id, "accessory_options")

def get_base_price(product_id):
    return get_metafield(product_id, "base_price_cents")


def get_products():
    url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/products.json?limit=10&fields=id,title,images,variants"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        products = res.json().get("products", [])

        # Simplify product info for templates
        product_list = []
        for p in products:
            first_image = p["images"][0]["src"] if p.get("images") else ""
            first_price = p["variants"][0]["price"] if p.get("variants") else "N/A"
            product_list.append({
                "id": p["id"],
                "title": p["title"],
                "image": first_image,
                "price": first_price,
            })
        return product_list

    except Exception as e:
        print("⚠ Shopify API error:", e)
        return [
            {"id": "111", "title": "Palo Alto Sofa", "image": "/static/rfq_app/img/sofa.jpg", "price": "2500"},
            {"id": "112", "title": "Palo Alto Chair", "image": "/static/rfq_app/img/chair.jpg", "price": "1200"},
        ]
def get_collection_products(collection_id, limit=250):
    """
    Fetch ALL products from a Shopify collection (works for both smart + custom collections).
    """
    products = []

    # Step 1: get product IDs from Collects API
    collects_url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/collects.json?collection_id={collection_id}&limit={limit}"
    while collects_url:
        res = requests.get(collects_url, headers=headers, timeout=10)
        res.raise_for_status()
        collects = res.json().get("collects", [])
        product_ids = [str(c["product_id"]) for c in collects]
        if product_ids:
            # Step 2: fetch full product details
            ids_str = ",".join(product_ids)
            prod_url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/products.json?ids={ids_str}&fields=id,title,images,variants"
            pres = requests.get(prod_url, headers=headers, timeout=10)
            pres.raise_for_status()
            for p in pres.json().get("products", []):
                products.append({
                    "id": p["id"],
                    "title": p["title"],
                    "image": p["images"][0]["src"] if p.get("images") else "",
                    "price": p["variants"][0]["price"] if p.get("variants") else "N/A",
                })

        # handle pagination of collects
        link_header = res.headers.get("Link")
        if link_header and 'rel="next"' in link_header:
            start = link_header.find("<") + 1
            end = link_header.find(">")
            collects_url = link_header[start:end]
        else:
            collects_url = None

    return products
