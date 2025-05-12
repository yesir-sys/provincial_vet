from django.contrib import admin
from .models import VeterinarySupplyCategory, VeterinarySupply, VeterinarySupplyRequest

@admin.register(VeterinarySupplyCategory)
class VeterinarySupplyCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(VeterinarySupply)
class VeterinarySupplyAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'quantity', 'unit', 'expiration_date', 'stock_status')
    list_filter = ('category', 'unit')  # Removed stock_status since it's a property
    search_fields = ('name', 'batch_number')  # Removed supplier
    readonly_fields = ('stock_status',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category')  # Removed supplier
        }),
        ('Inventory Details', {
            'fields': ('quantity', 'unit', 'minimum_stock', 'critical_stock')
        }),
        ('Medical Information', {
            'fields': ('expiration_date', 'batch_number')
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )

@admin.register(VeterinarySupplyRequest)
class VeterinarySupplyRequestAdmin(admin.ModelAdmin):
    list_display = ('supply', 'quantity', 'requester', 'status', 'urgency', 'request_date')
    list_filter = ('status', 'urgency', 'supply__category')
    search_fields = ('supply__name', 'requester__username')
    actions = ['approve_requests']

    def approve_requests(self, request, queryset):
        queryset.update(status='approved', approved_by=request.user)
    approve_requests.short_description = "Approve selected requests"