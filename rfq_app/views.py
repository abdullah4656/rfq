import json
import logging
from django.shortcuts import render, redirect
from django.conf import settings
from django.utils.html import strip_tags
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse

from .shopify_api import (
    get_products_from_collection,
    get_product_price,
    get_fabrics,
    get_size,
    get_upholstery_style,
    get_base_option,
    get_rails,
    get_frame_finish,
    get_heights,
    get_frame_trim,
)
from .utils import safe_price, render_to_pdf, get_selected_option

logger = logging.getLogger(__name__)
COLLECTION_ID = "296548499652"

# Session keys for RFQ data
RFQ_SESSION_KEYS = [
    'product_id', 'fabric', 'fabric_sub', 'size', 'size_sub',
    'upholstery', 'upholstery_sub', 'base_option', 'base_option_sub',
    'rails', 'rails_sub', 'frame_finish', 'frame_finish_sub',
    'height', 'height_sub', 'frame_trim', 'frame_trim_sub',
    'customer_name', 'customer_email', 'notes'
]

def clear_rfq_session(request):
    """Clear only RFQ-related session data"""
    for key in RFQ_SESSION_KEYS:
        if key in request.session:
            del request.session[key]

def get_running_total(request, product_id, current_options=None):
    """Calculate running total with all selected options"""
    base_price = safe_price(get_product_price(product_id))
    total = base_price
    
    # Add prices for all selected options
    option_functions = [
        (get_fabrics, 'fabric', 'fabric_sub'),
        (get_size, 'size', 'size_sub'),
        (get_upholstery_style, 'upholstery', 'upholstery_sub'),
        (get_base_option, 'base_option', 'base_option_sub'),
        (get_rails, 'rails', 'rails_sub'),
        (get_frame_finish, 'frame_finish', 'frame_finish_sub'),
        (get_heights, 'height', 'height_sub'),
        (get_frame_trim, 'frame_trim', 'frame_trim_sub'),
    ]
    
    for get_func, main_key, sub_key in option_functions:
        main_val = request.session.get(main_key)
        if main_val:
            options = get_func(product_id) or []
            main_option = next((o for o in options if o.get("key") == main_val), None)
            if main_option:
                # Handle different price field names
                upcharge = main_option.get("upcharge_cents") or main_option.get("upcharge") or main_option.get("price") or 0
                total += safe_price(upcharge)
                
                sub_val = request.session.get(sub_key)
                if sub_val and main_option.get("sub_options"):
                    sub_option = next((s for s in main_option["sub_options"] if s.get("key") == sub_val), None)
                    if sub_option:
                        sub_upcharge = sub_option.get("upcharge_cents") or sub_option.get("upcharge") or sub_option.get("price") or 0
                        total += safe_price(sub_upcharge)
    
    return total

### STEP 1: Select Product (Optional - can be kept as entry point) ###
def step1_select_product(request):
    try:
        products = get_products_from_collection(COLLECTION_ID)
        if not products:
            return render(request, "rfq_app/step1_select_product.html", {
                "error": "No products available. Please try again later."
            })
        
        if request.method == "POST":
            product_id = request.POST.get("product_id")
            if product_id:
                clear_rfq_session(request)
                request.session["product_id"] = product_id
                return redirect("step2_fabrics", product_id=product_id)
            
            return render(request, "rfq_app/step1_select_product.html", {
                "products": products,
                "error": "Please select a product to continue."
            })

        return render(request, "rfq_app/step1_select_product.html", {"products": products})
    
    except Exception as e:
        logger.error(f"Error in step1_select_product: {e}")
        return render(request, "rfq_app/step1_select_product.html", {
            "error": "Failed to load products. Please try again."
        })

### STEP 2: Fabrics ###
def step2_fabrics(request, product_id):
    try:
        base_price = safe_price(get_product_price(product_id))
        fabrics = get_fabrics(product_id) or []
        
        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            fabrics = [f for f in fabrics if 
                      search_query.lower() in f.get('label', '').lower() or 
                      search_query.lower() in f.get('title', '').lower() or
                      search_query.lower() in f.get('description', '').lower() or
                      search_query.lower() in f.get('color', '').lower()]
        
        # Skip step if no fabric options
        if not fabrics:
            return redirect("step3_size", product_id=product_id)

        # Calculate prices for main and sub-options with enhanced handling
        for f in fabrics:
            # Handle different price field names
            upcharge = f.get("upcharge_cents") or f.get("upcharge") or f.get("price") or 0
            f["price"] = safe_price(upcharge)
            
            for sub in f.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("fabric")
            if not selected:
                return render(request, "rfq_app/step2_fabrics.html", {
                    "fabrics": fabrics,
                    "base_price": base_price,
                    "running_total": get_running_total(request, product_id),
                    "error": "Please select a fabric to continue.",
                    "search_query": search_query,
                    "show_search": True,
                    "options": fabrics,
                    "product_id": product_id
                })

            # Handle sub-options: "ParentKey-SubKey"
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["fabric"] = parent_key
            request.session["fabric_sub"] = sub_key
            return redirect("step3_size", product_id=product_id)

        return render(request, "rfq_app/step2_fabrics.html", {
            "fabrics": fabrics,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "options": fabrics,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step2_fabrics: {e}")
        return render(request, "rfq_app/step2_fabrics.html", {
            "error": "Failed to load fabric options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 3: Size ###
def step3_size(request, product_id):
    try:
        base_price = safe_price(get_product_price(product_id))
        sizes = get_size(product_id) or []

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            sizes = [s for s in sizes if 
                    search_query.lower() in s.get('label', '').lower() or 
                    search_query.lower() in s.get('title', '').lower() or
                    search_query.lower() in s.get('description', '').lower() or
                    search_query.lower() in s.get('dimensions', '').lower()]

        # If no sizes at all, skip this step
        if not sizes:
            return redirect("step4_upholstery", product_id=product_id)

        # Add prices to main + sub-options with enhanced handling
        for s in sizes:
            # Handle different price field names
            upcharge = s.get("upcharge_cents") or s.get("upcharge") or s.get("price") or 0
            s["price"] = safe_price(upcharge)
            
            for sub in s.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("size")
            if not selected:
                return render(request, "rfq_app/step3_size.html", {
                    "sizes": sizes,
                    "error": "Please select a size.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "options": sizes,
                    "product_id": product_id
                })

            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["size"] = parent_key
            request.session["size_sub"] = sub_key
            return redirect("step4_upholstery", product_id=product_id)

        return render(request, "rfq_app/step3_size.html", {
            "sizes": sizes,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "options": sizes,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step3_size: {e}")
        return render(request, "rfq_app/step3_size.html", {
            "error": "Failed to load size options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 4: Upholstery ###
def step4_upholstery(request, product_id):
    try:
        options = get_upholstery_style(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('style', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("upholstery")
            if not selected:
                return render(request, "rfq_app/step4_upholstery.html", {
                    "options": options,
                    "error": "Please select an upholstery style.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "options_list": options,
                    "product_id": product_id
                })

            # Split parent / sub-option if needed
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["upholstery"] = parent_key
            request.session["upholstery_sub"] = sub_key
            return redirect("step5_base", product_id=product_id)

        return render(request, "rfq_app/step4_upholstery.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "options_list": options,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step4_upholstery: {e}")
        return render(request, "rfq_app/step4_upholstery.html", {
            "error": "Failed to load upholstery options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 5: Base ###
def step5_base(request, product_id):
    try:
        options = get_base_option(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('style', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("base")
            if not selected:
                return render(request, "rfq_app/step5_base.html", {
                    "options": options,
                    "error": "Please select a base option.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id
                })

            # Split parent / sub-option if needed
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["base_option"] = parent_key
            request.session["base_option_sub"] = sub_key
            return redirect("step6_rails", product_id=product_id)

        return render(request, "rfq_app/step5_base.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step5_base: {e}")
        return render(request, "rfq_app/step5_base.html", {
            "error": "Failed to load base options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 6: Rails ###
def step6_rails(request, product_id):
    try:
        options = get_rails(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('style', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("rails")
            if not selected:
                return render(request, "rfq_app/step6_rails.html", {
                    "options": options,
                    "error": "Please select a rail option.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id
                })

            # Split parent / sub-option if needed
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["rails"] = parent_key
            request.session["rails_sub"] = sub_key
            return redirect("step7_frame_finish", product_id=product_id)

        return render(request, "rfq_app/step6_rails.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step6_rails: {e}")
        return render(request, "rfq_app/step6_rails.html", {
            "error": "Failed to load rail options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 7: Frame Finish ###
def step7_frame_finish(request, product_id):
    try:
        options = get_frame_finish(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('finish_type', '').lower() or
                      search_query.lower() in o.get('color', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("frame_finish")
            if not selected:
                return render(request, "rfq_app/step7_frame_finish.html", {
                    "options": options,
                    "error": "Please select a frame finish.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["frame_finish"] = parent_key
            request.session["frame_finish_sub"] = sub_key
            return redirect("step8_height", product_id=product_id)

        return render(request, "rfq_app/step7_frame_finish.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step7_frame_finish: {e}")
        return render(request, "rfq_app/step7_frame_finish.html", {
            "error": "Failed to load frame finish options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 8: Height ###
def step8_height(request, product_id):
    try:
        options = get_heights(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('height_value', '').lower() or
                      search_query.lower() in o.get('size', '').lower()]

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("height")
            if not selected:
                return render(request, "rfq_app/step8_height.html", {
                    "options": options,
                    "error": "Please select a height option.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id
                })

            # Handle parent / sub-option
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["height"] = parent_key
            request.session["height_sub"] = sub_key
            return redirect("step9_frame_trim", product_id=product_id)

        return render(request, "rfq_app/step8_height.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step8_height: {e}")
        return render(request, "rfq_app/step8_height.html", {
            "error": "Failed to load height options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 9: Frame Trim ###
def step9_frame_trim(request, product_id):
    try:
        options = get_frame_trim(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('trim_type', '').lower() or
                      search_query.lower() in o.get('material', '').lower() or
                      search_query.lower() in o.get('style', '').lower()]

        # Add prices for main + sub-options with enhanced handling

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            selected = request.POST.get("frame_trim")
            if not selected:
                return render(request, "rfq_app/step9_frame_trim.html", {
                    "options": options,
                    "error": "Please select a frame trim option.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id
                })

            # Handle parent / sub-option
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["frame_trim"] = parent_key
            request.session["frame_trim_sub"] = sub_key
            return redirect("step10_customer_info", product_id=product_id)

        return render(request, "rfq_app/step9_frame_trim.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id
        })
    
    except Exception as e:
        logger.error(f"Error in step9_frame_trim: {e}")
        return render(request, "rfq_app/step9_frame_trim.html", {
            "error": "Failed to load frame trim options. Please try again.",
            "show_search": True,
            "product_id": product_id
        })

### STEP 10: Customer Info ###
def step10_customer_info(request, product_id):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        notes = request.POST.get("notes", "").strip()

        # Basic validation
        if not name:
            return render(request, "rfq_app/step10.html", {
                "error": "Please enter your name.",
                "product_id": product_id
            })
        
        if not email or "@" not in email:
            return render(request, "rfq_app/step10.html", {
                "error": "Please enter a valid email address.",
                "product_id": product_id
            })

        request.session["customer_name"] = name
        request.session["customer_email"] = email
        request.session["notes"] = notes

        try:
            # Recalculate total and lookup selections
            base_price = safe_price(get_product_price(product_id))
            total = base_price

            def find_selected(options, main_key, sub_key=None):
                main = next((o for o in options if o.get("key") == main_key), None)
                if not main:
                    return None
                # Handle different price field names
                upcharge = main.get("upcharge_cents") or main.get("upcharge") or main.get("price") or 0
                
                # Return the SIMPLE structure that matches your email template
                choice = {
                    "title": main.get("title") or main.get("label"),  # Simple title field
                    "price": safe_price(upcharge)  # Simple price field
                }
                
                if sub_key:
                    sub = next((s for s in main.get("sub_options", []) if s.get("key") == sub_key), None)
                    if sub:
                        sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                        choice.update({
                            "sub_title": sub.get("title") or sub.get("label"),
                            "sub_price": safe_price(sub_upcharge)
                        })
                
                return choice
            # Get all options
            fabric = find_selected(get_fabrics(product_id) or [], request.session.get("fabric"), request.session.get("fabric_sub"))
            size = find_selected(get_size(product_id) or [], request.session.get("size"), request.session.get("size_sub"))
            upholstery = find_selected(get_upholstery_style(product_id) or [], request.session.get("upholstery"), request.session.get("upholstery_sub"))
            base_option = find_selected(get_base_option(product_id) or [], request.session.get("base_option"), request.session.get("base_option_sub"))
            rails = find_selected(get_rails(product_id) or [], request.session.get("rails"), request.session.get("rails_sub"))
            frame_finish = find_selected(get_frame_finish(product_id) or [], request.session.get("frame_finish"), request.session.get("frame_finish_sub"))
            height = find_selected(get_heights(product_id) or [], request.session.get("height"), request.session.get("height_sub"))
            frame_trim = find_selected(get_frame_trim(product_id) or [], request.session.get("frame_trim"), request.session.get("frame_trim_sub"))

            # Add prices
            for choice in [fabric, size, upholstery, base_option, rails, frame_finish, height, frame_trim]:
                if choice:
                    total += choice.get("price", 0) + choice.get("sub_price", 0)

            # Build context
            context = {
                "product_id": product_id,
                "base_price": base_price,
                "fabric": fabric,
                "size": size,
                "upholstery": upholstery,
                "base_option": base_option,
                "rails": rails,
                "frame_finish": frame_finish,
                "height": height,
                "frame_trim": frame_trim,
                "grand_total": total,
                "customer_name": name,
                "customer_email": email,
                "notes": notes,
            }

            # Render email templates
            html_message = render_to_string("rfq_app/email_summary.html", context)
            plain_message = strip_tags(html_message)

            # Recipients
            recipients = ["abdullahyasin3848@gmail.com"]
            if email:
                recipients.append(email)

            # Build email with attachment
            email_msg = EmailMultiAlternatives(
                subject=f"New RFQ from {name}",
                body=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            email_msg.attach_alternative(html_message, "text/html")

            # Attach PDF
            pdf_bytes = render_to_pdf("rfq_app/email_summary.html", context)
            if pdf_bytes:
                email_msg.attach("RFQ_Summary.pdf", pdf_bytes, "application/pdf")

            # Send
            email_msg.send(fail_silently=False)

            return redirect("rfq_summary", product_id=product_id)

        except Exception as e:
            logger.error(f"Error sending email in step10: {e}")
            return render(request, "rfq_app/step10.html", {
                "error": "Failed to send your request. Please try again.",
                "product_id": product_id
            })

    # GET → customer form
    return render(request, "rfq_app/step10.html", {
        "running_total": get_running_total(request, product_id),
        "product_id": product_id
    })

### Summary Views ###
def rfq_summary(request, product_id):
    try:
        base_price = safe_price(get_product_price(product_id))

        # Use helper for all options
        selected_fabric, fabric_price = get_selected_option(get_fabrics, "fabric", product_id, request, safe_price)
        selected_size, size_price = get_selected_option(get_size, "size", product_id, request, safe_price)
        selected_upholstery, upholstery_price = get_selected_option(get_upholstery_style, "upholstery", product_id, request, safe_price)
        selected_base, base_option_price = get_selected_option(get_base_option, "base_option", product_id, request, safe_price)
        selected_rails, rails_price = get_selected_option(get_rails, "rails", product_id, request, safe_price)
        selected_finish, finish_price = get_selected_option(get_frame_finish, "frame_finish", product_id, request, safe_price)
        selected_height, height_price = get_selected_option(get_heights, "height", product_id, request, safe_price)
        selected_trim, trim_price = get_selected_option(get_frame_trim, "frame_trim", product_id, request, safe_price)

        # Total
        total = (
            base_price + fabric_price + size_price + upholstery_price +
            base_option_price + rails_price + finish_price +
            height_price + trim_price
        )

        context = {
            "product_id": product_id,
            "base_price": base_price,
            "fabric": selected_fabric,
            "size": selected_size,
            "upholstery": selected_upholstery,
            "base_option": selected_base,
            "rails": selected_rails,
            "frame_finish": selected_finish,
            "height": selected_height,
            "frame_trim": selected_trim,
            "grand_total": total,
            # Customer info
            "customer_name": request.session.get("customer_name"),
            "customer_email": request.session.get("customer_email"),
            "notes": request.session.get("notes"),
        }

        return render(request, "rfq_app/summary.html", context)
    
    except Exception as e:
        logger.error(f"Error in rfq_summary: {e}")
        return render(request, "rfq_app/summary.html", {
            "error": "Failed to load summary. Please try again.",
            "product_id": product_id
        })

def rfq_summary_pdf(request, product_id):
    try:
        base_price = safe_price(get_product_price(product_id))

        # Use the SAME find_selected function as step10_customer_info
        def find_selected(options, main_key, sub_key=None):
            main = next((o for o in options if o.get("key") == main_key), None)
            if not main:
                return None
            # Handle different price field names
            upcharge = main.get("upcharge_cents") or main.get("upcharge") or main.get("price") or 0
            
            # Return the SIMPLE structure that matches your email template
            choice = {
                "title": main.get("title") or main.get("label"),  # Simple title field
                "price": safe_price(upcharge)  # Simple price field
            }
            
            if sub_key:
                sub = next((s for s in main.get("sub_options", []) if s.get("key") == sub_key), None)
                if sub:
                    sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                    choice.update({
                        "sub_title": sub.get("title") or sub.get("label"),
                        "sub_price": safe_price(sub_upcharge)
                    })
            
            return choice

        # Get options using the SAME function as email
        fabric = find_selected(get_fabrics(product_id) or [], request.session.get("fabric"), request.session.get("fabric_sub"))
        size = find_selected(get_size(product_id) or [], request.session.get("size"), request.session.get("size_sub"))
        upholstery = find_selected(get_upholstery_style(product_id) or [], request.session.get("upholstery"), request.session.get("upholstery_sub"))
        base_option = find_selected(get_base_option(product_id) or [], request.session.get("base_option"), request.session.get("base_option_sub"))
        rails = find_selected(get_rails(product_id) or [], request.session.get("rails"), request.session.get("rails_sub"))
        frame_finish = find_selected(get_frame_finish(product_id) or [], request.session.get("frame_finish"), request.session.get("frame_finish_sub"))
        height = find_selected(get_heights(product_id) or [], request.session.get("height"), request.session.get("height_sub"))
        frame_trim = find_selected(get_frame_trim(product_id) or [], request.session.get("frame_trim"), request.session.get("frame_trim_sub"))

        # Calculate total
        total = base_price
        for choice in [fabric, size, upholstery, base_option, rails, frame_finish, height, frame_trim]:
            if choice:
                total += choice.get("price", 0) + choice.get("sub_price", 0)

        context = {
            "product_id": product_id,
            "base_price": base_price,
            "fabric": fabric,
            "size": size,
            "upholstery": upholstery,
            "base_option": base_option,
            "rails": rails,
            "frame_finish": frame_finish,
            "height": height,
            "frame_trim": frame_trim,
            "grand_total": total,
            "customer_name": request.session.get("customer_name"),
            "customer_email": request.session.get("customer_email"),
            "notes": request.session.get("notes"),
        }

        # Use the SAME template as email for consistency
        pdf = render_to_pdf("rfq_app/email_summary.html", context)
        if pdf:
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = "attachment; filename=RFQ_Summary.pdf"
            return response
        return HttpResponse("Error generating PDF", status=500)
    
    except Exception as e:
        logger.error(f"Error in rfq_summary_pdf: {e}")
        return HttpResponse("Error generating PDF", status=500)
def start_rfq_from_shopify(request):
    """Start RFQ process from Shopify product link"""
    shopify_product_id = request.GET.get('shopify_product_id')
    product_title = request.GET.get('product_title', '')
    product_price = request.GET.get('product_price', '0')
    product_image = request.GET.get('product_image', '')
    
    if shopify_product_id:
        # Clear any existing RFQ session
        clear_rfq_session(request)
        
        # Store the Shopify product info in session
        request.session['shopify_product_id'] = shopify_product_id
        request.session['product_title'] = product_title
        request.session['product_price'] = product_price
        request.session['product_image'] = product_image
        
        # Store the product ID in session for backward compatibility
        request.session['product_id'] = shopify_product_id
        
        # Redirect to the first step of your RFQ process with product_id in URL
        return redirect('step2_fabrics', product_id=shopify_product_id)
    
    # If no product ID provided, go to normal start
    return redirect('step1_select_product')