from django.db import models

class RFQ(models.Model):
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    product_name = models.CharField(max_length=200)
    fabric = models.CharField(max_length=200, blank=True, null=True)
    trim = models.CharField(max_length=200, blank=True, null=True)
    accessories = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"RFQ for {self.product_name} by {self.customer_name}"
class RFQCollection(models.Model):
    title = models.CharField(max_length=200)
    shopify_collection_id = models.CharField(max_length=50)

    def __str__(self):
        return self.title