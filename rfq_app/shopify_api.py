import requests
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "").strip()
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()

# Ensure https:// prefix
if SHOPIFY_STORE_URL and not SHOPIFY_STORE_URL.startswith("http"):
    SHOPIFY_STORE_URL = "https://" + SHOPIFY_STORE_URL

headers = {
    "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
    "Content-Type": "application/json"
}

def make_shopify_request(url):
    """Make a request to Shopify API with error handling"""
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        return res
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify API request failed: {e}")
        return None

def get_products_from_collection(collection_id, limit=50):
    """Fetch products belonging to a specific Shopify collection."""
    try:
        # Step 1: get product IDs via collects
        collects_url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/collects.json?collection_id={collection_id}&limit={limit}"
        res = make_shopify_request(collects_url)
        if not res:
            return []
            
        collects = res.json().get("collects", [])
        product_ids = [str(c["product_id"]) for c in collects]

        if not product_ids:
            return []

        # Step 2: fetch product details
        ids_str = ",".join(product_ids)
        prod_url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/products.json?ids={ids_str}"
        pres = make_shopify_request(prod_url)
        if not pres:
            return []

        products = []
        for p in pres.json().get("products", []):
            variants = p.get("variants", [])
            price = float(variants[0]["price"]) if variants and variants[0].get("price") else 0.0
            image = p.get("image", {}).get("src", "")
            products.append({
                "id": p["id"],
                "title": p["title"],
                "price": price,
                "image": image,
            })
        return products

    except Exception as e:
        logger.error(f"Error fetching collection {collection_id}: {e}")
        return []

def get_product_price(product_id):
    """Return product price as float (from first variant)."""
    try:
        url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/products/{product_id}.json"
        res = make_shopify_request(url)
        if not res:
            return 0.0
            
        product = res.json().get("product", {})
        price = product.get("variants", [{}])[0].get("price", "0")
        return float(price) if price else 0.0
    except Exception as e:
        logger.error(f"Error fetching price for {product_id}: {e}")
        return 0.0

def get_metafield(product_id, key, default=None):
    """Fetch metafield and parse JSON value safely."""
    url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/products/{product_id}/metafields.json"
    try:
        res = make_shopify_request(url)
        if not res:
            return default or []
            
        metafields = res.json().get("metafields", [])
        for m in metafields:
            if m["namespace"] == "rfq" and m["key"] == key:
                try:
                    value = m["value"]
                    if isinstance(value, str):
                        return json.loads(value)
                    return value
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to parse metafield {key} for product {product_id}")
                    return default or []
        return default or []
    except Exception as e:
        logger.error(f"Error fetching metafield {key}: {e}")
        return default or []

# --- Option fetchers ---
def get_fabrics(product_id): 
    return get_metafield(product_id, "fabric_options", [])

def get_size(product_id): 
    return get_metafield(product_id, "size_options", [])

def get_upholstery_style(product_id): 
    return get_metafield(product_id, "upholstery_style_options", [])

def get_base_option(product_id): 
    return get_metafield(product_id, "base_options", [])

def get_rails(product_id): 
    return get_metafield(product_id, "rails_option", [])

def get_frame_finish(product_id): 
    return get_metafield(product_id, "frame_finish_option", [])

def get_heights(product_id): 
    return get_metafield(product_id, "height_options", [])

def get_frame_trim(product_id): 
    return get_metafield(product_id, "frame_trim_options", [])