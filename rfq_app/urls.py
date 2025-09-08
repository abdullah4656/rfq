from django.urls import path
from . import views

urlpatterns = [
    path("", views.step1_select_product, name="step1_select_product"),
    path("rfq/step2/", views.step2_fabrics, name="step2_fabrics"),
    path("rfq/step3/", views.step3_size, name="step3_size"),
    path("rfq/step4/", views.step4_upholstery, name="step4_upholstery"),
    path("rfq/step5/", views.step5_base, name="step5_base"),
    path("rfq/step6/", views.step6_rails, name="step6_rails"),
    path("rfq/step7/", views.step7_frame_finish, name="step7_frame_finish"),
    path("rfq/step8/", views.step8_height, name="step8_height"),
    path("rfq/step9/", views.step9_frame_trim, name="step9_frame_trim"),
    path("rfq/step10/", views.step10_customer_info, name="step10_customer_info"),
   path("rfq/summary/", views.rfq_summary, name="rfq_summary"),
   path("rfq/summary/pdf/", views.rfq_summary_pdf, name="rfq_summary_pdf"), path('rfq/start/', views.start_rfq_from_shopify, name='start_rfq_from_shopify'),
]
