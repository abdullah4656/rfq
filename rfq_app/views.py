import json
import logging
from django.shortcuts import render, redirect
from django.conf import settings
from django.utils.html import strip_tags
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse
import datetime
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
    
    get_finish_trim,
    get_pricing,
    get_drawer_sidepannel,
    get_seat,
    get_decorative_hardware_finish,
    get_decorative_hardware_style,
    get_top,
    get_optional_drawer_and_side_panels_trim
    
)
from .utils import safe_price, render_to_pdf, get_selected_option

logger = logging.getLogger(__name__)
COLLECTION_ID = "296548499652"

# Session keys for RFQ data
# Session keys for RFQ data
RFQ_SESSION_KEYS = [
    'product_id', 'fabric', 'fabric_sub', 'size', 'size_sub',
    'upholstery', 'upholstery_sub', 'base_option', 'base_option_sub',
    'rails', 'rails_sub', 'frame_finish', 'frame_finish_sub',
    'height', 'height_sub', 'frame_trim', 'frame_trim_sub',
    'finish_trim', 'finish_trim_sub', 'pricing', 'pricing_sub',
    'drawer_sidepannel', 'drawer_sidepannel_sub', 'seat', 'seat_sub',
    'decorative_hardware_finish', 'decorative_hardware_finish_sub',
    'decorative_hardware_style', 'decorative_hardware_style_sub',
    'top', 'top_sub', 'optional_drawer_side_panels_trim', 'optional_drawer_side_panels_trim_sub',
    'customer_name', 'customer_email', 'notes',
    'shopify_product_id', 'product_title', 'product_price', 'product_image'
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
        (get_finish_trim, 'finish_trim', 'finish_trim_sub'),
        (get_pricing, 'pricing', 'pricing_sub'),
        (get_drawer_sidepannel, 'drawer_sidepannel', 'drawer_sidepannel_sub'),
        (get_seat, 'seat', 'seat_sub'),
        (get_decorative_hardware_finish, 'decorative_hardware_finish', 'decorative_hardware_finish_sub'),
        (get_decorative_hardware_style, 'decorative_hardware_style', 'decorative_hardware_style_sub'),
        (get_top, 'top', 'top_sub'),
        (get_optional_drawer_and_side_panels_trim, 'optional_drawer_side_panels_trim', 'optional_drawer_side_panels_trim_sub'),
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
### STEP 1: Select Product ###
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

### STEP 2: Fabrics (MANDATORY - No Skip Button) ###
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
        
        # Skip step if no fabric options - automatically go to next available step
        if not fabrics:
            next_step = get_next_step('step2_fabrics', product_id)
            return redirect(next_step, product_id=product_id)

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
                    "product_id": product_id,
                    "is_optional": False  # Fabric is mandatory
                })

            # Handle sub-options: "ParentKey-SubKey"
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["fabric"] = parent_key
            request.session["fabric_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step2_fabrics', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step2_fabrics.html", {
            "fabrics": fabrics,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "options": fabrics,
            "product_id": product_id,
            "is_optional": False  # Fabric is mandatory
        })
    
    except Exception as e:
        logger.error(f"Error in step2_fabrics: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step2_fabrics', product_id)
        return redirect(next_step, product_id=product_id)

### STEP 3: Size (OPTIONAL - With Skip Button) ###
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

        # If no sizes at all, skip this step - automatically go to next available step
        if not sizes:
            next_step = get_next_step('step3_size', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices to main + sub-options with enhanced handling
        for s in sizes:
            # Handle different price field names
            upcharge = s.get("upcharge_cents") or s.get("upcharge") or s.get("price") or 0
            s["price"] = safe_price(upcharge)
            
            for sub in s.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Clear any previous selection for size
                request.session['size'] = None
                request.session['size_sub'] = None

                
                # Redirect to next step
                next_step = get_next_step('step3_size', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("size")
            if not selected:
                return render(request, "rfq_app/step3_size.html", {
                    "sizes": sizes,
                    "error": "Please select a size or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "options": sizes,
                    "product_id": product_id,
                    "is_optional": True  # Size is optional
                })

            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["size"] = parent_key
            request.session["size_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step3_size', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step3_size.html", {
            "sizes": sizes,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "options": sizes,
            "product_id": product_id,
            "is_optional": True  # Size is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step3_size: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step3_size', product_id)
        return redirect(next_step, product_id=product_id)

### STEP 4: Upholstery (OPTIONAL - With Skip Button) ###
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

        # Skip step if no upholstery options - automatically go to next available step
        if not options:
            next_step = get_next_step('step4_upholstery', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Clear any previous selection for upholstery
                request.session['upholstery'] = None
                request.session['upholstery_sub'] = None

                
                # Redirect to next step
                next_step = get_next_step('step4_upholstery', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("upholstery")
            if not selected:
                return render(request, "rfq_app/step4_upholstery.html", {
                    "options": options,
                    "error": "Please select an upholstery style or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "options_list": options,
                    "product_id": product_id,
                    "is_optional": True  # Upholstery is optional
                })

            # Split parent / sub-option if needed
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["upholstery"] = parent_key
            request.session["upholstery_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step4_upholstery', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step4_upholstery.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "options_list": options,
            "product_id": product_id,
            "is_optional": True  # Upholstery is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step4_upholstery: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step4_upholstery', product_id)
        return redirect(next_step, product_id=product_id)

### STEP 5: Base (OPTIONAL - With Skip Button) ###
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

        # Skip step if no base options - automatically go to next available step
        if not options:
            next_step = get_next_step('step5_base', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Clear any previous selection for base
                request.session['base_option'] = None
                request.session['base_option_sub'] = None

                
                # Redirect to next step
                next_step = get_next_step('step5_base', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("base")
            if not selected:
                return render(request, "rfq_app/step5_base.html", {
                    "options": options,
                    "error": "Please select a base option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Base is optional
                })

            # Split parent / sub-option if needed
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["base_option"] = parent_key
            request.session["base_option_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step5_base', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step5_base.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Base is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step5_base: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step5_base', product_id)
        return redirect(next_step, product_id=product_id)

### STEP 6: Rails (OPTIONAL - With Skip Button) ###
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

        # Skip step if no rail options - automatically go to next available step
        if not options:
            next_step = get_next_step('step6_rails', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Clear any previous selection for rails
                request.session['rails'] = None
                request.session['rails_sub'] = None

                
                # Redirect to next step
                next_step = get_next_step('step6_rails', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("rails")
            if not selected:
                return render(request, "rfq_app/step6_rails.html", {
                    "options": options,
                    "error": "Please select a rail option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Rails are optional
                })

            # Split parent / sub-option if needed
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["rails"] = parent_key
            request.session["rails_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step6_rails', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step6_rails.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Rails are optional
        })
    
    except Exception as e:
        logger.error(f"Error in step6_rails: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step6_rails', product_id)
        return redirect(next_step, product_id=product_id)

### STEP 7: Frame Finish (OPTIONAL - With Skip Button) ###
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

        # Skip step if no frame finish options - automatically go to next available step
        if not options:
            next_step = get_next_step('step7_frame_finish', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Clear any previous selection for frame finish
                request.session['frame_finish'] = None
                request.session['frame_finish_sub'] = None

                
                # Redirect to next step
                next_step = get_next_step('step7_frame_finish', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("frame_finish")
            if not selected:
                return render(request, "rfq_app/step7_frame_finish.html", {
                    "options": options,
                    "error": "Please select a frame finish or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Frame finish is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["frame_finish"] = parent_key
            request.session["frame_finish_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step7_frame_finish', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step7_frame_finish.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Frame finish is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step7_frame_finish: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step7_frame_finish', product_id)
        return redirect(next_step, product_id=product_id)

### STEP 8: Height (OPTIONAL - With Skip Button) ###
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

        # Skip step if no height options - automatically go to next available step
        if not options:
            next_step = get_next_step('step8_height', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Clear any previous selection for height
                request.session['height'] = None
                request.session['height_sub'] = None

                
                # Redirect to next step
                next_step = get_next_step('step8_height', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("height")
            if not selected:
                return render(request, "rfq_app/step8_height.html", {
                    "options": options,
                    "error": "Please select a height option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Height is optional
                })

            # Handle parent / sub-option
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["height"] = parent_key
            request.session["height_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step8_height', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step8_height.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Height is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step8_height: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step8_height', product_id)
        return redirect(next_step, product_id=product_id)

### STEP 9: Frame Trim (OPTIONAL - With Skip Button) ###
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
                      search_query.lower() in o.get('trim_style', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Skip step if no frame trim options - automatically go to next available step
        if not options:
            next_step = get_next_step('step9_frame_trim', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Clear any previous selection for frame trim
                request.session['frame_trim'] = None
                request.session['frame_trim_sub'] = None

                            
                # Redirect to next step
                next_step = get_next_step('step9_frame_trim', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("frame_trim")
            if not selected:
                return render(request, "rfq_app/step9_frame_trim.html", {
                    "options": options,
                    "error": "Please select a frame trim option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Frame trim is optional
                })

            # Handle parent / sub-option
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["frame_trim"] = parent_key
            request.session["frame_trim_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step9_frame_trim', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step9_frame_trim.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Frame trim is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step9_frame_trim: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step9_frame_trim', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 10: Finish Trim (OPTIONAL - With Skip Button) ###
def step10_finish_trim(request, product_id):
    try:
        options = get_finish_trim(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('trim_style', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Skip step if no finish trim options - automatically go to next available step
        if not options:
            next_step = get_next_step('step10_finish_trim', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark finish trim as explicitly skipped by setting to None
                request.session['finish_trim'] = None
                request.session['finish_trim_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step10_finish_trim', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("finish_trim")
            if not selected:
                return render(request, "rfq_app/step10_finish_trim.html", {
                    "options": options,
                    "error": "Please select a finish trim option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Finish trim is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["finish_trim"] = parent_key
            request.session["finish_trim_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step10_finish_trim', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step10_finish_trim.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Finish trim is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step10_finish_trim: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step10_finish_trim', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 11: Pricing (OPTIONAL - With Skip Button) ###
def step11_pricing(request, product_id):
    try:
        options = get_pricing(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('price_type', '').lower() or
                      search_query.lower() in o.get('category', '').lower()]

        # Skip step if no pricing options - automatically go to next available step
        if not options:
            next_step = get_next_step('step11_pricing', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark pricing as explicitly skipped by setting to None
                request.session['pricing'] = None
                request.session['pricing_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step11_pricing', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("pricing")
            if not selected:
                return render(request, "rfq_app/step11_pricing.html", {
                    "options": options,
                    "error": "Please select a pricing option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Pricing is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["pricing"] = parent_key
            request.session["pricing_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step11_pricing', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step11_pricing.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Pricing is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step11_pricing: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step11_pricing', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 12: Drawer Side Panel (OPTIONAL - With Skip Button) ###
def step12_drawer_sidepannel(request, product_id):
    try:
        options = get_drawer_sidepannel(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('panel_type', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Skip step if no drawer side panel options - automatically go to next available step
        if not options:
            next_step = get_next_step('step12_drawer_sidepannel', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark drawer side panel as explicitly skipped by setting to None
                request.session['drawer_sidepannel'] = None
                request.session['drawer_sidepannel_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step12_drawer_sidepannel', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("drawer_sidepannel")
            if not selected:
                return render(request, "rfq_app/step12_drawer_sidepannel.html", {
                    "options": options,
                    "error": "Please select a drawer side panel option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Drawer side panel is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["drawer_sidepannel"] = parent_key
            request.session["drawer_sidepannel_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step12_drawer_sidepannel', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step12_drawer_sidepannel.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Drawer side panel is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step12_drawer_sidepannel: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step12_drawer_sidepannel', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 13: Seat (OPTIONAL - With Skip Button) ###
def step13_seat(request, product_id):
    try:
        options = get_seat(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('seat_type', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Skip step if no seat options - automatically go to next available step
        if not options:
            next_step = get_next_step('step13_seat', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark seat as explicitly skipped by setting to None
                request.session['seat'] = None
                request.session['seat_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step13_seat', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("seat")
            if not selected:
                return render(request, "rfq_app/step13_seat.html", {
                    "options": options,
                    "error": "Please select a seat option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Seat is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["seat"] = parent_key
            request.session["seat_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step13_seat', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step13_seat.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Seat is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step13_seat: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step13_seat', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 14: Decorative Hardware Finish (OPTIONAL - With Skip Button) ###
def step14_decorative_hardware_finish(request, product_id):
    try:
        options = get_decorative_hardware_finish(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('finish_type', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Skip step if no decorative hardware finish options - automatically go to next available step
        if not options:
            next_step = get_next_step('step14_decorative_hardware_finish', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark decorative hardware finish as explicitly skipped by setting to None
                request.session['decorative_hardware_finish'] = None
                request.session['decorative_hardware_finish_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step14_decorative_hardware_finish', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("decorative_hardware_finish")
            if not selected:
                return render(request, "rfq_app/step14_decorative_hardware_finish.html", {
                    "options": options,
                    "error": "Please select a decorative hardware finish option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Decorative hardware finish is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["decorative_hardware_finish"] = parent_key
            request.session["decorative_hardware_finish_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step14_decorative_hardware_finish', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step14_decorative_hardware_finish.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Decorative hardware finish is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step14_decorative_hardware_finish: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step14_decorative_hardware_finish', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 15: Decorative Hardware Style (OPTIONAL - With Skip Button) ###
def step15_decorative_hardware_style(request, product_id):
    try:
        options = get_decorative_hardware_style(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('style_type', '').lower() or
                      search_query.lower() in o.get('design', '').lower()]

        # Skip step if no decorative hardware style options - automatically go to next available step
        if not options:
            next_step = get_next_step('step15_decorative_hardware_style', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark decorative hardware style as explicitly skipped by setting to None
                request.session['decorative_hardware_style'] = None
                request.session['decorative_hardware_style_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step15_decorative_hardware_style', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("decorative_hardware_style")
            if not selected:
                return render(request, "rfq_app/step15_decorative_hardware_style.html", {
                    "options": options,
                    "error": "Please select a decorative hardware style option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Decorative hardware style is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["decorative_hardware_style"] = parent_key
            request.session["decorative_hardware_style_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step15_decorative_hardware_style', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step15_decorative_hardware_style.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Decorative hardware style is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step15_decorative_hardware_style: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step15_decorative_hardware_style', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 16: Top (OPTIONAL - With Skip Button) ###
def step16_top(request, product_id):
    try:
        options = get_top(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('top_type', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Skip step if no top options - automatically go to next available step
        if not options:
            next_step = get_next_step('step16_top', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark top as explicitly skipped by setting to None
                request.session['top'] = None
                request.session['top_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step16_top', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("top")
            if not selected:
                return render(request, "rfq_app/step16_top.html", {
                    "options": options,
                    "error": "Please select a top option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Top is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["top"] = parent_key
            request.session["top_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step16_top', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step16_top.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Top is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step16_top: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step16_top', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 17: Optional Drawer and Side Panels Trim (OPTIONAL - With Skip Button) ###
def step17_optional_drawer_side_panels_trim(request, product_id):
    try:
        options = get_optional_drawer_and_side_panels_trim(product_id) or []
        base_price = safe_price(get_product_price(product_id))

        # SEARCH FUNCTIONALITY
        search_query = request.GET.get('search', '')
        if search_query:
            options = [o for o in options if 
                      search_query.lower() in o.get('label', '').lower() or 
                      search_query.lower() in o.get('title', '').lower() or
                      search_query.lower() in o.get('description', '').lower() or
                      search_query.lower() in o.get('trim_type', '').lower() or
                      search_query.lower() in o.get('material', '').lower()]

        # Skip step if no optional drawer and side panels trim options - automatically go to next available step
        if not options:
            next_step = get_next_step('step17_optional_drawer_side_panels_trim', product_id)
            return redirect(next_step, product_id=product_id)

        # Add prices for main + sub-options with enhanced handling
        for o in options:
            # Handle different price field names
            upcharge = o.get("upcharge_cents") or o.get("upcharge") or o.get("price") or 0
            o["price"] = safe_price(upcharge)
            
            for sub in o.get("sub_options", []):
                sub_upcharge = sub.get("upcharge_cents") or sub.get("upcharge") or sub.get("price") or 0
                sub["price"] = safe_price(sub_upcharge)

        if request.method == "POST":
            # Check if user clicked skip button
            if 'skip' in request.POST:
                # Mark optional drawer and side panels trim as explicitly skipped by setting to None
                request.session['optional_drawer_side_panels_trim'] = None
                request.session['optional_drawer_side_panels_trim_sub'] = None
                
                # Redirect to next step
                next_step = get_next_step('step17_optional_drawer_side_panels_trim', product_id)
                return redirect(next_step, product_id=product_id)
                
            selected = request.POST.get("optional_drawer_side_panels_trim")
            if not selected:
                return render(request, "rfq_app/step17_optional_drawer_side_panels_trim.html", {
                    "options": options,
                    "error": "Please select an optional drawer and side panels trim option or click skip to continue.",
                    "running_total": get_running_total(request, product_id),
                    "search_query": search_query,
                    "show_search": True,
                    "product_id": product_id,
                    "is_optional": True  # Optional drawer and side panels trim is optional
                })

            # Handle parent / sub-option split
            if "-" in selected:
                parent_key, sub_key = selected.split("-", 1)
            else:
                parent_key, sub_key = selected, None

            request.session["optional_drawer_side_panels_trim"] = parent_key
            request.session["optional_drawer_side_panels_trim_sub"] = sub_key
            
            # Use automatic next step detection instead of hardcoded redirect
            next_step = get_next_step('step17_optional_drawer_side_panels_trim', product_id)
            return redirect(next_step, product_id=product_id)

        return render(request, "rfq_app/step17_optional_drawer_side_panels_trim.html", {
            "options": options,
            "running_total": get_running_total(request, product_id),
            "base_price": base_price,
            "search_query": search_query,
            "show_search": True,
            "product_id": product_id,
            "is_optional": True  # Optional drawer and side panels trim is optional
        })
    
    except Exception as e:
        logger.error(f"Error in step17_optional_drawer_side_panels_trim: {e}")
        # On error, try to go to next step instead of showing error page
        next_step = get_next_step('step17_optional_drawer_side_panels_trim', product_id)
        return redirect(next_step, product_id=product_id)
### STEP 10: Customer Info ###
### STEP 18: Customer Info ###
def step18_customer_info(request, product_id):
    # Calculate running total once to use in both GET and POST scenarios
    running_total = get_running_total(request, product_id)
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        notes = request.POST.get("notes", "").strip()

        # Basic validation
        if not name:
            return render(request, "rfq_app/step18_customer_info.html", {
                "error": "Please enter your name.",
                "product_id": product_id,
                "running_total": running_total  # Add running total to error context
            })
        
        if not email or "@" not in email:
            return render(request, "rfq_app/step18_customer_info.html", {
                "error": "Please enter a valid email address.",
                "product_id": product_id,
                "running_total": running_total  # Add running total to error context
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
            
            # Get all options including the new ones
            fabric = find_selected(get_fabrics(product_id) or [], request.session.get("fabric"), request.session.get("fabric_sub"))
            size = find_selected(get_size(product_id) or [], request.session.get("size"), request.session.get("size_sub"))
            upholstery = find_selected(get_upholstery_style(product_id) or [], request.session.get("upholstery"), request.session.get("upholstery_sub"))
            base_option = find_selected(get_base_option(product_id) or [], request.session.get("base_option"), request.session.get("base_option_sub"))
            rails = find_selected(get_rails(product_id) or [], request.session.get("rails"), request.session.get("rails_sub"))
            frame_finish = find_selected(get_frame_finish(product_id) or [], request.session.get("frame_finish"), request.session.get("frame_finish_sub"))
            height = find_selected(get_heights(product_id) or [], request.session.get("height"), request.session.get("height_sub"))
            frame_trim = find_selected(get_frame_trim(product_id) or [], request.session.get("frame_trim"), request.session.get("frame_trim_sub"))
            finish_trim = find_selected(get_finish_trim(product_id) or [], request.session.get("finish_trim"), request.session.get("finish_trim_sub"))
            pricing = find_selected(get_pricing(product_id) or [], request.session.get("pricing"), request.session.get("pricing_sub"))
            drawer_sidepannel = find_selected(get_drawer_sidepannel(product_id) or [], request.session.get("drawer_sidepannel"), request.session.get("drawer_sidepannel_sub"))
            seat = find_selected(get_seat(product_id) or [], request.session.get("seat"), request.session.get("seat_sub"))
            decorative_hardware_finish = find_selected(get_decorative_hardware_finish(product_id) or [], request.session.get("decorative_hardware_finish"), request.session.get("decorative_hardware_finish_sub"))
            decorative_hardware_style = find_selected(get_decorative_hardware_style(product_id) or [], request.session.get("decorative_hardware_style"), request.session.get("decorative_hardware_style_sub"))
            top = find_selected(get_top(product_id) or [], request.session.get("top"), request.session.get("top_sub"))
            optional_drawer_side_panels_trim = find_selected(get_optional_drawer_and_side_panels_trim(product_id) or [], request.session.get("optional_drawer_side_panels_trim"), request.session.get("optional_drawer_side_panels_trim_sub"))

            # Add prices
            for choice in [fabric, size, upholstery, base_option, rails, frame_finish, height, frame_trim, 
                          finish_trim, pricing, drawer_sidepannel, seat, decorative_hardware_finish, 
                          decorative_hardware_style, top, optional_drawer_side_panels_trim]:
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
                "finish_trim": finish_trim,
                "pricing": pricing,
                "drawer_sidepannel": drawer_sidepannel,
                "seat": seat,
                "decorative_hardware_finish": decorative_hardware_finish,
                "decorative_hardware_style": decorative_hardware_style,
                "top": top,
                "optional_drawer_side_panels_trim": optional_drawer_side_panels_trim,
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
            logger.error(f"Error sending email in step18_customer_info: {e}")
            return render(request, "rfq_app/step18_customer_info.html", {
                "error": "Failed to send your request. Please try again.",
                "product_id": product_id,
                "running_total": running_total  # Add running total to error context
            })

    # GET → customer form
    return render(request, "rfq_app/step18_customer_info.html", {
        "running_total": running_total,
        "product_id": product_id
    })
def rfq_summary(request, product_id):
    try:
        base_price = safe_price(get_product_price(product_id))

        # Use helper for all options - handle None results gracefully
        selected_fabric, fabric_price = get_selected_option(get_fabrics, "fabric", product_id, request, safe_price)
        selected_size, size_price = get_selected_option(get_size, "size", product_id, request, safe_price)
        selected_upholstery, upholstery_price = get_selected_option(get_upholstery_style, "upholstery", product_id, request, safe_price)
        selected_base, base_option_price = get_selected_option(get_base_option, "base_option", product_id, request, safe_price)
        selected_rails, rails_price = get_selected_option(get_rails, "rails", product_id, request, safe_price)
        selected_finish, finish_price = get_selected_option(get_frame_finish, "frame_finish", product_id, request, safe_price)
        selected_height, height_price = get_selected_option(get_heights, "height", product_id, request, safe_price)
        selected_trim, trim_price = get_selected_option(get_frame_trim, "frame_trim", product_id, request, safe_price)
        
        # ADD THE NEW OPTIONS HERE:
        selected_finish_trim, finish_trim_price = get_selected_option(get_finish_trim, "finish_trim", product_id, request, safe_price)
        selected_pricing, pricing_price = get_selected_option(get_pricing, "pricing", product_id, request, safe_price)
        selected_drawer_sidepannel, drawer_sidepannel_price = get_selected_option(get_drawer_sidepannel, "drawer_sidepannel", product_id, request, safe_price)
        selected_seat, seat_price = get_selected_option(get_seat, "seat", product_id, request, safe_price)
        selected_decorative_hardware_finish, decorative_hardware_finish_price = get_selected_option(get_decorative_hardware_finish, "decorative_hardware_finish", product_id, request, safe_price)
        selected_decorative_hardware_style, decorative_hardware_style_price = get_selected_option(get_decorative_hardware_style, "decorative_hardware_style", product_id, request, safe_price)
        selected_top, top_price = get_selected_option(get_top, "top", product_id, request, safe_price)
        selected_optional_drawer_side_panels_trim, optional_drawer_side_panels_trim_price = get_selected_option(get_optional_drawer_and_side_panels_trim, "optional_drawer_side_panels_trim", product_id, request, safe_price)

        # Total - ensure all prices are valid numbers
        total = base_price
        for price in [fabric_price, size_price, upholstery_price, base_option_price, 
                     rails_price, finish_price, height_price, trim_price,
                     # ADD THE NEW PRICES HERE:
                     finish_trim_price, pricing_price, drawer_sidepannel_price,
                     seat_price, decorative_hardware_finish_price, decorative_hardware_style_price,
                     top_price, optional_drawer_side_panels_trim_price]:
            total += price if price else 0

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
            # ADD THE NEW OPTIONS TO CONTEXT:
            "finish_trim": selected_finish_trim,
            "pricing": selected_pricing,
            "drawer_sidepannel": selected_drawer_sidepannel,
            "seat": selected_seat,
            "decorative_hardware_finish": selected_decorative_hardware_finish,
            "decorative_hardware_style": selected_decorative_hardware_style,
            "top": selected_top,
            "optional_drawer_side_panels_trim": selected_optional_drawer_side_panels_trim,
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

        # Use the SAME find_selected function as step18_customer_info
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
        finish_trim = find_selected(get_finish_trim(product_id) or [], request.session.get("finish_trim"), request.session.get("finish_trim_sub"))
        pricing = find_selected(get_pricing(product_id) or [], request.session.get("pricing"), request.session.get("pricing_sub"))
        drawer_sidepannel = find_selected(get_drawer_sidepannel(product_id) or [], request.session.get("drawer_sidepannel"), request.session.get("drawer_sidepannel_sub"))
        seat = find_selected(get_seat(product_id) or [], request.session.get("seat"), request.session.get("seat_sub"))
        decorative_hardware_finish = find_selected(get_decorative_hardware_finish(product_id) or [], request.session.get("decorative_hardware_finish"), request.session.get("decorative_hardware_finish_sub"))
        decorative_hardware_style = find_selected(get_decorative_hardware_style(product_id) or [], request.session.get("decorative_hardware_style"), request.session.get("decorative_hardware_style_sub"))
        top = find_selected(get_top(product_id) or [], request.session.get("top"), request.session.get("top_sub"))
        optional_drawer_side_panels_trim = find_selected(get_optional_drawer_and_side_panels_trim(product_id) or [], request.session.get("optional_drawer_side_panels_trim"), request.session.get("optional_drawer_side_panels_trim_sub"))

        # Calculate total - handle None values gracefully
        total = base_price
        for choice in [fabric, size, upholstery, base_option, rails, frame_finish, height, frame_trim,
                      finish_trim, pricing, drawer_sidepannel, seat, decorative_hardware_finish,
                      decorative_hardware_style, top, optional_drawer_side_panels_trim]:
            if choice:
                total += (choice.get("price", 0) or 0) + (choice.get("sub_price", 0) or 0)

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
            "finish_trim": finish_trim,
            "pricing": pricing,
            "drawer_sidepannel": drawer_sidepannel,
            "seat": seat,
            "decorative_hardware_finish": decorative_hardware_finish,
            "decorative_hardware_style": decorative_hardware_style,
            "top": top,
            "optional_drawer_side_panels_trim": optional_drawer_side_panels_trim,
            "grand_total": total,
            "customer_name": request.session.get("customer_name"),
            "customer_email": request.session.get("customer_email"),
            "notes": request.session.get("notes"),
        }

        # Use the SAME template as email for consistency
        pdf = render_to_pdf("rfq_app/email_summary.html", context)
        if pdf:
            # Create a filename with customer name and timestamp if available
            customer_name = request.session.get("customer_name", "").replace(" ", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"RFQ_Summary_{customer_name}_{timestamp}.pdf" if customer_name else "RFQ_Summary.pdf"
            
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        
        logger.error("Failed to generate PDF - render_to_pdf returned None")
        return HttpResponse("Error generating PDF", status=500)
    
    except Exception as e:
        logger.error(f"Error in rfq_summary_pdf: {e}")
        return HttpResponse("Error generating PDF", status=500)
def start_rfq_from_shopify(request):
    """Start RFQ process from Shopify product link with automatic step detection"""
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
        
        # Find the first available step with options
        step_order = [
            ('step2_fabrics', get_fabrics),
            ('step3_size', get_size),
            ('step4_upholstery', get_upholstery_style),
            ('step5_base', get_base_option),
            ('step6_rails', get_rails),
            ('step7_frame_finish', get_frame_finish),
            ('step8_height', get_heights),
            ('step9_frame_trim', get_frame_trim),
            ('step10_finish_trim', get_finish_trim),
            ('step11_pricing', get_pricing),
            ('step12_drawer_sidepannel', get_drawer_sidepannel),
            ('step13_seat', get_seat),
            ('step14_decorative_hardware_finish', get_decorative_hardware_finish),
            ('step15_decorative_hardware_style', get_decorative_hardware_style),
            ('step16_top', get_top),
            ('step17_optional_drawer_side_panels_trim', get_optional_drawer_and_side_panels_trim),
            ('step18_customer_info', None),  # Always available as fallback
        ]
        
        # Find first step with available options
        for step_name, option_function in step_order:
            if step_name == 'step18_customer_info':
                # If we reach customer info, use it as fallback
                break
                
            # Check if this step has options
            try:
                options = option_function(shopify_product_id) if option_function else []
                if options:
                    # Found a step with options, redirect to it
                    return redirect(step_name, product_id=shopify_product_id)
            except Exception as e:
                logger.error(f"Error checking options for {step_name}: {e}")
                # If there's an error checking options, continue to next step
                continue
        
        # If no steps with options found, go directly to customer info
        return redirect('step18_customer_info', product_id=shopify_product_id)
    
    # If no product ID provided, go to normal start
    return redirect('step1_select_product')
def get_next_step(current_step, product_id):
    """
    Determine the next available step based on which options are available
    Returns the next step URL name
    """
    step_order = [
        ('step2_fabrics', get_fabrics),
        ('step3_size', get_size),
        ('step4_upholstery', get_upholstery_style),
        ('step5_base', get_base_option),
        ('step6_rails', get_rails),
        ('step7_frame_finish', get_frame_finish),
        ('step8_height', get_heights),
        ('step9_frame_trim', get_frame_trim),
        ('step10_finish_trim', get_finish_trim),
        ('step11_pricing', get_pricing),
        ('step12_drawer_sidepannel', get_drawer_sidepannel),
        ('step13_seat', get_seat),
        ('step14_decorative_hardware_finish', get_decorative_hardware_finish),
        ('step15_decorative_hardware_style', get_decorative_hardware_style),
        ('step16_top', get_top),
        ('step17_optional_drawer_side_panels_trim', get_optional_drawer_and_side_panels_trim),
        ('step18_customer_info', None),  # Always show customer info step
    ]
    
    # Find current step index
    current_index = None
    for i, (step_name, _) in enumerate(step_order):
        if step_name == current_step:
            current_index = i
            break
    
    if current_index is None:
        logger.warning(f"Current step '{current_step}' not found in step order. Defaulting to customer info.")
        return 'step18_customer_info'  # Default to last step
    
    # Find next step with available options
    for i in range(current_index + 1, len(step_order)):
        step_name, option_function = step_order[i]
        
        # Customer info is always available
        if step_name == 'step18_customer_info':
            return step_name
        
        # Check if this step has options (with robust error handling)
        try:
            options = option_function(product_id) if option_function else []
            if options and any(options):  # If options exist and are not empty, go to this step
                return step_name
        except Exception as e:
            logger.error(f"Error checking options for {step_name} with product {product_id}: {e}")
            # If there's an error checking options, continue to next step
            continue
    
    # If no more steps with options, go to customer info
    return 'step18_customer_info'