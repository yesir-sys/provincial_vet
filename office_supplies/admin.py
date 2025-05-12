from django.contrib import admin
from .models import OfficeSupplyCategory, OfficeSupply, OfficeSupplyRequest

@admin.register(OfficeSupplyCategory)
class OfficeSupplyCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(OfficeSupply)
class OfficeSupplyAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'quantity', 'unit', 'reorder_level', 'needs_reorder')
    list_filter = ('category', 'unit')  # Removed needs_reorder since it's a property
    search_fields = ('name', 'model_number')  # Removed supplier
    readonly_fields = ('needs_reorder',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category')  # Removed supplier
        }),
        ('Inventory Details', {
            'fields': ('quantity', 'unit', 'reorder_level', 'location')
        }),
        ('Product Information', {
            'fields': ('model_number',)
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )

@admin.register(OfficeSupplyRequest)  # Changed from OfficeSupplyOrder
class OfficeSupplyRequestAdmin(admin.ModelAdmin):  # Changed class name
    list_display = ('supply', 'quantity', 'requester', 'status', 'request_date')  # Removed total_cost
    list_filter = ('status', 'supply__category')
    search_fields = ('supply__name',)  # Removed invoice_number
    readonly_fields = ('request_date',)  # Changed from order_date
    fieldsets = (
        ('Request Details', {  # Changed from Order Details
            'fields': ('supply', 'quantity', 'status')
        }),
        ('Purpose', {  # Added new fieldset for request-specific fields
            'fields': ('purpose',)
        }),
        ('Approval Info', {
            'fields': ('requester', 'approved_by', 'approval_date')  # Updated fields
        }),
    )