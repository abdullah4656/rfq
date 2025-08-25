from django.contrib import admin

# Register your models here.
from .models import RFQCollection

@admin.register(RFQCollection)
class RFQCollectionAdmin(admin.ModelAdmin):
    list_display = ("title", "shopify_collection_id")