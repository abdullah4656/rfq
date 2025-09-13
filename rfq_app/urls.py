from django.urls import path
from . import views

urlpatterns = [
    path("", views.step1_select_product, name="step1_select_product"),
    path("rfq/<str:product_id>/fabrics/", views.step2_fabrics, name="step2_fabrics"),
    path("rfq/<str:product_id>/size/", views.step3_size, name="step3_size"),
    path("rfq/<str:product_id>/upholstery/", views.step4_upholstery, name="step4_upholstery"),
    path("rfq/<str:product_id>/base/", views.step5_base, name="step5_base"),
    path("rfq/<str:product_id>/rails/", views.step6_rails, name="step6_rails"),
    path("rfq/<str:product_id>/frame-finish/", views.step7_frame_finish, name="step7_frame_finish"),
    path("rfq/<str:product_id>/height/", views.step8_height, name="step8_height"),
    path("rfq/<str:product_id>/frame-trim/", views.step9_frame_trim, name="step9_frame_trim"),
    path("rfq/<str:product_id>/finish-trim/", views.step10_finish_trim, name="step10_finish_trim"),
    path("rfq/<str:product_id>/pricing/", views.step11_pricing, name="step11_pricing"),
    path("rfq/<str:product_id>/drawer-sidepanel/", views.step12_drawer_sidepannel, name="step12_drawer_sidepannel"),
    path("rfq/<str:product_id>/seat/", views.step13_seat, name="step13_seat"),
    path("rfq/<str:product_id>/decorative-hardware-finish/", views.step14_decorative_hardware_finish, name="step14_decorative_hardware_finish"),
    path("rfq/<str:product_id>/decorative-hardware-style/", views.step15_decorative_hardware_style, name="step15_decorative_hardware_style"),
    path("rfq/<str:product_id>/top/", views.step16_top, name="step16_top"),
    path("rfq/<str:product_id>/optional-drawer-side-panels-trim/", views.step17_optional_drawer_side_panels_trim, name="step17_optional_drawer_side_panels_trim"),
    path("rfq/<str:product_id>/customer-info/", views.step18_customer_info, name="step18_customer_info"),
    path("rfq/<str:product_id>/summary/", views.rfq_summary, name="rfq_summary"),
    path("rfq/<str:product_id>/summary/pdf/", views.rfq_summary_pdf, name="rfq_summary_pdf"),
    path('rfq/start/', views.start_rfq_from_shopify, name='start_rfq_from_shopify'),
]