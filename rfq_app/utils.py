# rfq_app/utils.py
from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa

def render_to_pdf(template_src, context_dict={}):
    """
    Render a Django template into a PDF file.
    Returns raw PDF bytes if successful, else None.
    """
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    if not pdf.err:
        return result.getvalue()
    return None


def safe_price(value):
    """Convert cents or string to float price in dollars."""
    try:
        if isinstance(value, str) and value.isdigit():
            return round(float(value) / 100, 2)
        return round(float(value), 2)
    except Exception:
        return 0.0


def get_selected_option(getter, session_key, product_id, request, safe_price_func):
    """
    Generic helper to fetch the selected option or sub-option with its price.
    Returns (selected_object, total_price).
    
    Enhanced to handle skipped options (where session_key exists but is None)
    """
    # Check if this option was explicitly skipped (session key exists but is None)
    if session_key in request.session and request.session.get(session_key) is None:
        return None, 0
        
    options = getter(product_id) or []

    # Enhanced price handling - handle different field names
    for o in options:
        # Handle different price field names
        upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
        o["price"] = safe_price_func(upcharge)
        
        for sub in o.get("sub_options", []):
            sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
            sub["price"] = safe_price_func(sub_upcharge)

    selected_key = request.session.get(session_key)
    selected_sub = request.session.get(f"{session_key}_sub")

    selected = None
    total_price = 0

    if selected_key:
        main = next((o for o in options if o.get("key") == selected_key), None)
        if main:
            total_price += main.get("price", 0)
            selected = {
                "main_title": main.get("title") or main.get("label"),
                "main_price": main.get("price", 0)
            }
            
            if selected_sub:
                sub = next((s for s in main.get("sub_options", []) if s.get("key") == selected_sub), None)
                if sub:
                    total_price += sub.get("price", 0)
                    selected.update({
                        "sub_title": sub.get("title") or sub.get("label"),
                        "sub_price": sub.get("price", 0)
                    })

    return selected, total_price