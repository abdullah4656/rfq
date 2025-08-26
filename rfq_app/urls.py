from django.urls import path
from . import views

urlpatterns = [
    path("rfq/start/", views.start_rfq, name="start_rfq"),
    path("", views.step1_select_product, name="step1_select_product"),
    path("fabrics/", views.step2_fabrics, name="step2_fabrics"),
    path("trims/", views.step3_trims, name="step3_trims"),
    path("accessories/", views.step4_accessories, name="step4_accessories"),
    path("customer-info/", views.step5_customer_info, name="step5_customer_info"),
    path("summary/<int:rfq_id>/", views.rfq_summary, name="rfq_summary"),
]
