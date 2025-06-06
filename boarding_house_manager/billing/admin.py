from django.contrib import admin
from .models import Room, Tenant, Bill, Payment, ElectricityReading
from django.urls import path, reverse
from django.utils.html import format_html
from .views import financial_summary_report, occupancy_report

# Basic registration for models that don't have a custom admin yet or are simple
admin.site.register(Room) # Can be enhanced later if needed

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'room_display', 'lease_start_date', 'lease_end_date', 'is_active', 'fixed_water_charge', 'fixed_wifi_charge')
    list_filter = ('is_active', 'room__room_number') # Filter by room number
    search_fields = ('full_name', 'email', 'phone_number', 'room__room_number')
    autocomplete_fields = ['room'] # Autocomplete for room selection
    fieldsets = (
        (None, {
            'fields': ('full_name', 'user', 'room', 'is_active')
        }),
        ('Fixed Charges', {
            'fields': ('fixed_water_charge', 'fixed_wifi_charge'),
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'email'),
            'classes': ('collapse',)
        }),
        ('Lease Details', {
            'fields': ('lease_start_date', 'lease_end_date'),
            'classes': ('collapse',)
        }),
    )
    def room_display(self, obj):
        if obj.room:
            return obj.room.room_number
        return "-"
    room_display.short_description = 'Room'
    room_display.admin_order_field = 'room__room_number'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('bill_summary_link', 'tenant_name_link', 'amount_paid', 'payment_date', 'payment_method')
    list_filter = ('payment_date', 'payment_method', 'tenant__full_name')
    search_fields = ('bill__id', 'bill__description', 'tenant__full_name', 'notes') # Search by bill ID
    autocomplete_fields = ['bill', 'tenant']
    date_hierarchy = 'payment_date'

    def bill_summary_link(self, obj):
        if obj.bill:
            link = reverse("admin:billing_bill_change", args=[obj.bill.id])
            return format_html('<a href="{}">Bill ID {} ({}, Amount: {})</a>', link, obj.bill.id, obj.bill.bill_type, obj.bill.amount)
        return "N/A"
    bill_summary_link.short_description = 'Bill'
    bill_summary_link.admin_order_field = 'bill'


    def tenant_name_link(self, obj):
        if obj.tenant:
            link = reverse("admin:billing_tenant_change", args=[obj.tenant.id])
            return format_html('<a href="{}">{}</a>', link, obj.tenant.full_name)
        return "N/A"
    tenant_name_link.short_description = 'Tenant'
    tenant_name_link.admin_order_field = 'tenant'


@admin.register(ElectricityReading)
class ElectricityReadingAdmin(admin.ModelAdmin):
    list_display = ('tenant_link', 'reading_date', 'reading_value', 'previous_reading_value', 'consumption', 'unit_price', 'is_billed')
    list_filter = ('tenant__full_name', 'reading_date', 'is_billed')
    search_fields = ('tenant__full_name', 'reading_value')
    autocomplete_fields = ['tenant']
    date_hierarchy = 'reading_date'

    def tenant_link(self, obj):
        if obj.tenant:
            link = reverse("admin:billing_tenant_change", args=[obj.tenant.id])
            return format_html('<a href="{}">{}</a>', link, obj.tenant.full_name)
        return "N/A"
    tenant_link.short_description = 'Tenant'
    tenant_link.admin_order_field = 'tenant'


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('id','__str__', 'tenant_link', 'bill_type', 'amount', 'due_date', 'is_paid', 'date_created')
    list_filter = ('is_paid', 'bill_type', 'due_date', 'tenant__full_name')
    search_fields = ['id', 'description', 'tenant__full_name', 'tenant__room__room_number']
    autocomplete_fields = ['tenant']
    date_hierarchy = 'due_date'
    ordering = ('-due_date',)
    list_editable = ('is_paid', 'amount', 'due_date') # Retained from previous version

    fieldsets = (
        (None, {
            'fields': ('tenant', 'bill_type', 'amount', 'description')
        }),
        ('Status & Dates', {
            'fields': ('is_paid', 'due_date', 'date_created', 'date_updated'), # Added date_created, date_updated
        }),
    )
    readonly_fields = ('date_created', 'date_updated')

    def tenant_link(self, obj):
        if obj.tenant_id: # Use tenant_id for efficiency, avoids loading tenant object if not needed
            link = reverse("admin:billing_tenant_change", args=[obj.tenant_id])
            return format_html('<a href="{}">{}</a>', link, obj.tenant.full_name)
        return "N/A"
    tenant_link.short_description = 'Tenant'
    tenant_link.admin_order_field = 'tenant' # Allows sorting by tenant

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('reports/financial-summary/', self.admin_site.admin_view(financial_summary_report), name='billing_financial_summary'),
            path('reports/occupancy/', self.admin_site.admin_view(occupancy_report), name='billing_occupancy_report'),
        ]
        return custom_urls + urls
