from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

class Room(models.Model):
    room_number = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    base_rent = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.room_number

class Tenant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    lease_start_date = models.DateField()
    lease_end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    fixed_water_charge = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True, default=None,
        help_text="Fixed monthly water charge for this tenant. Leave blank or 0 if not applicable or included in rent."
    )
    fixed_wifi_charge = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True, default=None,
        help_text="Fixed monthly WiFi charge for this tenant. Leave blank or 0 if not applicable."
    )

    def __str__(self):
        return self.full_name

class Bill(models.Model):
    BILL_TYPE_CHOICES = [
        ('Rent', 'Rent'),
        ('Electricity', 'Electricity'),
        ('Water', 'Water'),
        ('WiFi', 'WiFi'),
        ('Other', 'Other'),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    bill_type = models.CharField(max_length=20, choices=BILL_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    is_paid = models.BooleanField(default=False)
    description = models.TextField(blank=True, help_text="Details for 'Other' bill type or specific notes")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_bill_type_display()} Bill for {self.tenant.full_name} due on {self.due_date}"

class Payment(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=255, blank=True, help_text="e.g., Cash, Bank Transfer")
    notes = models.TextField(blank=True)
    date_recorded = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment of {self.amount_paid} for {self.bill}"

# Signal handlers for Payment model
@receiver(post_save, sender=Payment)
def payment_saved_or_updated(sender, instance, created, **kwargs):
    if instance.bill:
        related_bill = instance.bill
        # Ensure we are working with the correct Bill class if using string sender
        # Bill_model = apps.get_model('billing', 'Bill')
        # related_bill = Bill_model.objects.get(pk=instance.bill.pk)

        current_total_paid = related_bill.payment_set.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

        status_changed = False
        if current_total_paid >= related_bill.amount:
            if not related_bill.is_paid:
                related_bill.is_paid = True
                status_changed = True
        else:
            if related_bill.is_paid:
                related_bill.is_paid = False
                status_changed = True

        if status_changed:
            related_bill.save(update_fields=['is_paid', 'date_updated'])

@receiver(post_delete, sender=Payment)
def payment_deleted(sender, instance, **kwargs):
    if instance.bill:
        related_bill = instance.bill
        # Bill_model = apps.get_model('billing', 'Bill') # For string sender 'billing.Payment'

        try:
            # related_bill_obj = Bill_model.objects.get(pk=related_bill.pk) # Use if Bill_model is used
            related_bill.refresh_from_db() # Ensure we have the latest state if not using Bill_model approach
            current_total_paid = related_bill.payment_set.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

            status_changed = False
            if current_total_paid >= related_bill.amount:
                if not related_bill.is_paid:
                    related_bill.is_paid = True
                    status_changed = True
            else:
                if related_bill.is_paid:
                    related_bill.is_paid = False
                    status_changed = True

            if status_changed:
                related_bill.save(update_fields=['is_paid', 'date_updated'])
        except Bill.DoesNotExist: # Changed from related_bill.DoesNotExist to Bill.DoesNotExist
            # The bill was deleted, nothing to do.
            pass

class ElectricityReading(models.Model):
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, related_name='electricity_readings')
    reading_date = models.DateField()
    reading_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Current meter reading in kWh")
    previous_reading_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Meter reading value from the last bill")
    consumption = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated consumption (current - previous)")
    unit_price = models.DecimalField(max_digits=6, decimal_places=3, help_text="Price per kWh at the time of reading")
    is_billed = models.BooleanField(default=False, help_text="Has a bill been generated for this reading period?")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reading for {self.tenant} on {self.reading_date} - {self.reading_value} kWh"

    class Meta:
        ordering = ['-reading_date', '-created_at']
        unique_together = [['tenant', 'reading_date']] # Assuming one reading per day per tenant is sufficient
