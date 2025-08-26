from django.shortcuts import render, redirect
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import json

from .models import RFQ, RFQCollection
from .shopify_api import (
    get_collection_products,
    get_fabrics,
    get_trims,
    get_accessories,
    get_base_price,
)
from .utils import render_to_pdf


# ---------- Helper ----------
def safe_price(val):
    """Convert Shopify metafield value into float dollars safely."""
    try:
        if isinstance(val, list):  # e.g. []
            return 0
        if val in [None, "", "[]"]:
            return 0
        return int(val) / 100
    except (ValueError, TypeError):
        return 0
import requests
from .shopify_api import SHOPIFY_STORE_URL, headers

def get_product_by_id(product_id):
    """Fetch single product from Shopify"""
    url = f"{SHOPIFY_STORE_URL}/admin/api/2025-01/products/{product_id}.json"
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    p = res.json()["product"]
    return {
        "id": str(p["id"]),
        "title": p["title"],
        "image": p["images"][0]["src"] if p.get("images") else "",
        "price": p["variants"][0]["price"] if p.get("variants") else "N/A",
    }

def start_rfq(request):
    product_id = request.GET.get("product_id")
    if not product_id:
        return redirect("step1_select_product")  # fallback if no product passed

    product = get_product_by_id(product_id)

    # Save selection in session
    request.session["product_id"] = product["id"]
    request.session["product"] = product["title"]

    # Jump directly into fabrics step
    return redirect("step2_fabrics")

def step1_select_product(request):
    collection = RFQCollection.objects.first()
    products = []
    if collection:
        products = get_collection_products(collection.shopify_collection_id)

    query = request.GET.get("q", "").lower()
    if query:
        products = [p for p in products if query in p["title"].lower()]

    if request.method == "POST":
        product_data = request.POST.get("product")
        if not product_data:
            return render(request, "rfq_app/step1_select_product.html", {
                "products": products,
                "error": "Please select a product before continuing.",
                "query": query,
            })
        product_id, product_title = product_data.split("|", 1)
        request.session["product"] = product_title
        request.session["product_id"] = product_id
        return redirect("step2_fabrics")

    # ✅ Only fetch base price if a product_id is already chosen
    product_id = request.session.get("product_id")
    base_price = safe_price(get_base_price(product_id)) if product_id else 0

    return render(request, "rfq_app/step1_select_product.html", {
        "products": products,
        "base_price": base_price,
        "query": query,
    })

def step2_fabrics(request):
    base_price = safe_price(get_base_price(request.session["product_id"]))
    fabrics = json.loads(get_fabrics(request.session["product_id"]))
    for f in fabrics:
        f["price"] = safe_price(f.get("upcharge_cents"))

    # --- Search ---
    query = request.GET.get("q", "").lower()
    if query:
        fabrics = [f for f in fabrics if query in f["title"].lower()]

    if request.method == "POST":
        fabric = request.POST.get("fabric")
        if not fabric:
            return render(request, "rfq_app/step2_fabrics.html", {
                "fabrics": fabrics,
                "error": "Please select a fabric before continuing.",
                "running_total": base_price,
                "query": query,
            })
        request.session["fabric"] = fabric
        return redirect("step3_trims")

    selected = next((f for f in fabrics if f["key"] == request.session.get("fabric")), None)
    fabric_price = selected["price"] if selected else 0
    running_total = base_price + fabric_price

    return render(request, "rfq_app/step2_fabrics.html", {
        "fabrics": fabrics,
        "base_price": base_price,
        "running_total": running_total,
        "query": query,
    })

def step3_trims(request):
    base_price = safe_price(get_base_price(request.session["product_id"]))
    trims = json.loads(get_trims(request.session["product_id"]))
    for t in trims:
        t["price"] = safe_price(t.get("upcharge_cents"))

    # --- Search ---
    query = request.GET.get("q", "").lower()
    if query:
        trims = [t for t in trims if query in t["title"].lower()]

    if request.method == "POST":
        trim = request.POST.get("trim")
        if not trim:
            return render(request, "rfq_app/step3_trims.html", {
                "trims": trims,
                "error": "Please select a trim before continuing.",
                "query": query,
            })
        request.session["trim"] = trim
        return redirect("step4_accessories")

    fabrics = json.loads(get_fabrics(request.session["product_id"]))
    selected_fabric = next((f for f in fabrics if f["key"] == request.session.get("fabric")), None)
    fabric_price = safe_price(selected_fabric["upcharge_cents"]) if selected_fabric else 0

    selected_trim = next((t for t in trims if t["key"] == request.session.get("trim")), None)
    trim_price = selected_trim["price"] if selected_trim else 0

    running_total = base_price + fabric_price + trim_price

    return render(request, "rfq_app/step3_trims.html", {
        "trims": trims,
        "base_price": base_price,
        "running_total": running_total,
        "query": query,
    })
def step4_accessories(request):
    base_price = safe_price(get_base_price(request.session["product_id"]))
    fabrics = json.loads(get_fabrics(request.session["product_id"]))
    trims = json.loads(get_trims(request.session["product_id"]))

    selected_fabric = next((f for f in fabrics if f["key"] == request.session.get("fabric")), None)
    fabric_price = safe_price(selected_fabric["upcharge_cents"]) if selected_fabric else 0

    selected_trim = next((t for t in trims if t["key"] == request.session.get("trim")), None)
    trim_price = safe_price(selected_trim["upcharge_cents"]) if selected_trim else 0

    accessories = json.loads(get_accessories(request.session["product_id"]))
    for a in accessories:
        a["price"] = safe_price(a.get("upcharge_cents"))

    # --- Search ---
    query = request.GET.get("q", "").lower()
    if query:
        accessories = [a for a in accessories if query in a["title"].lower()]

    if request.method == "POST":
        request.session["accessories"] = request.POST.getlist("accessories")
        return redirect("step5_customer_info")

    selected_accessories = [a for a in accessories if a["key"] in request.session.get("accessories", [])]
    accessories_total = sum(a["price"] for a in selected_accessories)

    running_total = base_price + fabric_price + trim_price + accessories_total

    return render(request, "rfq_app/step4_accessories.html", {
        "accessories": accessories,
        "base_price": base_price,
        "running_total": running_total,
        "query": query,
    })

def step5_customer_info(request):
    product_id = request.session.get("product_id")
    if not product_id:
        return redirect("step1_select_product")

    base_price = safe_price(get_base_price(product_id))
    fabrics = json.loads(get_fabrics(product_id))
    trims = json.loads(get_trims(product_id))
    accessories = json.loads(get_accessories(product_id))

    # Attach prices
    for f in fabrics: f["price"] = safe_price(f.get("upcharge_cents"))
    for t in trims: t["price"] = safe_price(t.get("upcharge_cents"))
    for a in accessories: a["price"] = safe_price(a.get("upcharge_cents"))

    # Match user selections
    selected_fabric = next((f for f in fabrics if f["key"] == request.session.get("fabric")), None)
    selected_trim = next((t for t in trims if t["key"] == request.session.get("trim")), None)
    selected_accessories = [a for a in accessories if a["key"] in request.session.get("accessories", [])]

    fabric_price = selected_fabric["price"] if selected_fabric else 0
    trim_price = selected_trim["price"] if selected_trim else 0
    accessories_total = sum(a["price"] for a in selected_accessories)
    grand_total = base_price + fabric_price + trim_price + accessories_total

    if request.method == "POST":
        name = request.POST["name"]
        email = request.POST["email"]
        notes = request.POST.get("notes", "")

        rfq = RFQ.objects.create(
            customer_name=name,
            customer_email=email,
            product_name=request.session.get("product"),
            fabric=request.session.get("fabric"),
            trim=request.session.get("trim"),
            accessories=", ".join(request.session.get("accessories", [])),
            notes=notes,
        )

        # ----- Send Email -----
        context = {
            "rfq": rfq,
            "base_price": base_price,
            "fabric": selected_fabric,
            "trim": selected_trim,
            "accessories": selected_accessories,
            "fabric_price": fabric_price,
            "trim_price": trim_price,
            "accessories_total": accessories_total,
            "grand_total": grand_total,
        }
        subject = f"RFQ Summary - {rfq.product_name}"
        html_message = render_to_string("rfq_app/email_rfq.html", context)
        plain_message = strip_tags(html_message)
        to_emails = [email, "sales@yourcompany.com"]

        email_obj = EmailMultiAlternatives(subject, plain_message, None, to_emails)
        email_obj.attach_alternative(html_message, "text/html")
        email_obj.send()

        return redirect("rfq_summary", rfq_id=rfq.id)

    return render(request, "rfq_app/step5_customer_info.html", {
        "base_price": base_price,
        "fabric": selected_fabric,
        "trim": selected_trim,
        "accessories": selected_accessories,
        "fabric_price": fabric_price,
        "trim_price": trim_price,
        "accessories_total": accessories_total,
        "grand_total": grand_total,
    })

# ---------- Summary ----------
def rfq_summary(request, rfq_id):
    rfq = RFQ.objects.get(id=rfq_id)

    base_price = safe_price(get_base_price(request.session["product_id"]))
    fabrics = json.loads(get_fabrics(request.session["product_id"]))
    trims = json.loads(get_trims(request.session["product_id"]))
    accessories = json.loads(get_accessories(request.session["product_id"]))

    selected_fabric = next((f for f in fabrics if f["key"] == request.session.get("fabric")), None)
    selected_trim = next((t for t in trims if t["key"] == request.session.get("trim")), None)
    selected_accessories = [a for a in accessories if a["key"] in request.session.get("accessories", [])]

    fabric_price = safe_price(selected_fabric["upcharge_cents"]) if selected_fabric else 0
    trim_price = safe_price(selected_trim["upcharge_cents"]) if selected_trim else 0
    accessories_total = sum(safe_price(a["upcharge_cents"]) for a in selected_accessories)

    grand_total = base_price + fabric_price + trim_price + accessories_total

    context = {
        "rfq": rfq,
        "base_price": base_price,
        "fabric": selected_fabric,
        "trim": selected_trim,
        "accessories": selected_accessories,
        "fabric_price": fabric_price,
        "trim_price": trim_price,
        "accessories_total": accessories_total,
        "grand_total": grand_total,
    }
    return render(request, "rfq_app/rfq_summary.html", context)