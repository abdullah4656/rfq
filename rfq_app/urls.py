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
    path("rfq/<str:product_id>/customer-info/", views.step10_customer_info, name="step10_customer_info"),
    path("rfq/<str:product_id>/summary/", views.rfq_summary, name="rfq_summary"),
    path("rfq/<str:product_id>/summary/pdf/", views.rfq_summary_pdf, name="rfq_summary_pdf"),
    path('rfq/start/', views.start_rfq_from_shopify, name='start_rfq_from_shopify'),
]