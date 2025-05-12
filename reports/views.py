from django.views.generic import TemplateView, ListView
from django.db.models import Sum, Count, F, Q, When, Case
from django.utils import timezone
from django.http import HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import models
from django.core.cache import cache  # Add this import
from vet_supplies.models import VeterinarySupply, VeterinarySupplyRequest
from office_supplies.models import OfficeSupply, OfficeSupplyRequest
from .models import InventoryMovement
import csv
from django.db.models.functions import TruncDate
from datetime import timedelta
from django.core.serializers.json import DjangoJSONEncoder
import json

class DashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'reports/dashboard.html'
    
    def test_func(self):
        return self.request.user.is_staff
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        
        # Enhanced analytics
        analytics = self.get_analytics_data()
        context.update(analytics)
        
        # Get recent movements with caching
        context['movements'] = self.get_cached_movements()
        
        # Add filtered supplies if filter exists
        filter_param = self.request.GET.get('filter')
        if filter_param:
            context['current_filter'] = filter_param
            context['filtered_supplies'] = self.get_filtered_supplies(filter_param)
        
        return context

    def get_analytics_data(self):
        """Get consolidated analytics data"""
        today = timezone.now().date()
        analytics = {}

        # Stock status with percentage calculations
        stock_stats = self.get_stock_status()
        total_items = sum(sum(category.values()) for category in stock_stats.values())
        
        analytics['stock_status'] = stock_stats
        analytics['total_supplies'] = total_items
        analytics['stock_percentages'] = {
            level: {
                'vet': (stats['vet'] / total_items * 100) if total_items > 0 else 0,
                'office': (stats['office'] / total_items * 100) if total_items > 0 else 0
            }
            for level, stats in stock_stats.items()
        }

        # Extended expiring items data
        expiring = self.get_expiring_data(today)
        analytics['expiring_soon_count'] = expiring['counts']
        analytics['expiring_soon_percent'] = expiring['percentage']
        analytics['expiring_items'] = expiring['items']

        # Enhanced pending requests data
        pending = self.get_pending_data()
        analytics['pending_requests'] = pending['counts']
        analytics['pending_items'] = pending['items']
        analytics['pending_total'] = pending['total_requests']  # Changed from pending_value to pending_total

        # Activity trends
        activity = self.get_activity_trends()
        analytics['chart_data'] = activity['trends']
        analytics['type_chart_data'] = activity['distribution']
        analytics['activity_stats'] = activity['stats']

        return analytics

    def get_expiring_data(self, today):
        """Get detailed expiring items data"""
        thirty_days = today + timezone.timedelta(days=30)
        
        vet_expiring = VeterinarySupply.objects.filter(
            expiration_date__gt=today,
            expiration_date__lte=thirty_days
        )
        office_expiring = OfficeSupply.objects.filter(
            expiration_date__gt=today,
            expiration_date__lte=thirty_days
        )

        total_items = VeterinarySupply.objects.count() + OfficeSupply.objects.count()
        total_expiring = vet_expiring.count() + office_expiring.count()
        
        return {
            'counts': {
                'vet': vet_expiring.count(),
                'office': office_expiring.count()
            },
            'percentage': (total_expiring / total_items * 100) if total_items > 0 else 0,
            'items': {
                'vet': vet_expiring.values('name', 'expiration_date', 'quantity')[:5],
                'office': office_expiring.values('name', 'expiration_date', 'quantity')[:5]
            }
        }

    def get_pending_data(self):
        """Get enhanced pending requests data"""
        vet_pending = VeterinarySupplyRequest.objects.filter(status='pending')
        office_pending = OfficeSupplyRequest.objects.filter(status='pending')

        return {
            'counts': {
                'vet': vet_pending.count(),
                'office': office_pending.count()
            },
            'items': {
                'vet': vet_pending.select_related('supply', 'requester')[:5],
                'office': office_pending.select_related('supply', 'requester')[:5]
            },
            # Remove total_value calculation since price field doesn't exist
            'total_requests': {
                'vet': vet_pending.aggregate(
                    total=Count('id')
                )['total'] or 0,
                'office': office_pending.aggregate(
                    total=Count('id')
                )['total'] or 0
            }
        }

    def get_activity_trends(self):
        """Get enhanced activity trends"""
        today = timezone.now().date()
        last_30_days = today - timezone.timedelta(days=30)
        
        daily_movements = InventoryMovement.objects.filter(
            timestamp__date__gte=last_30_days
        ).annotate(
            date=TruncDate('timestamp')
        ).values('date', 'action', 'item_type').annotate(
            count=Count('id')
        ).order_by('date', 'action')

        dates = []
        actions_data = {
            'created': [],
            'restocked': [],
            'depleted': [],
            'request_approved': []
        }
        
        current_date = last_30_days
        while current_date <= today:
            dates.append(current_date.strftime('%Y-%m-%d'))
            movements_on_date = [m for m in daily_movements if m['date'] == current_date]
            
            for action in actions_data.keys():
                count = next(
                    (m['count'] for m in movements_on_date if m['action'] == action),
                    0
                )
                actions_data[action].append(count)
            
            current_date += timezone.timedelta(days=1)

        type_distribution = InventoryMovement.objects.filter(
            timestamp__date__gte=last_30_days
        ).values('item_type').annotate(
            count=Count('id')
        ).order_by('item_type')

        return {
            'trends': {
                'dates': dates,
                'series': [
                    {
                        'name': 'New Items',
                        'data': actions_data['created']
                    },
                    {
                        'name': 'Restocked',
                        'data': actions_data['restocked']
                    },
                    {
                        'name': 'Depleted',
                        'data': actions_data['depleted']
                    },
                    {
                        'name': 'Approved Requests',
                        'data': actions_data['request_approved']
                    }
                ]
            },
            'distribution': {
                'labels': [t['item_type'].title() for t in type_distribution],
                'series': [t['count'] for t in type_distribution]
            },
            'stats': {
                'total_movements': InventoryMovement.objects.count(),
                'today_movements': InventoryMovement.objects.filter(
                    timestamp__date=timezone.now().date()
                ).count(),
                'most_active_items': InventoryMovement.objects.values(
                    'item_name'
                ).annotate(
                    count=Count('id')
                ).order_by('-count')[:5]
            }
        }

    def get_stock_status(self):
        return {
            'low': {
                'vet': VeterinarySupply.objects.filter(quantity__lte=F('reorder_level')).count(),
                'office': OfficeSupply.objects.filter(quantity__lte=F('reorder_level')).count()
            },
            'warning': {
                'vet': VeterinarySupply.objects.filter(
                    quantity__gt=F('reorder_level'),
                    quantity__lte=F('minimum_stock')
                ).count(),
                'office': OfficeSupply.objects.filter(
                    quantity__gt=F('reorder_level'),
                    quantity__lte=F('minimum_stock')
                ).count()
            }
        }

    def get_low_stock_counts(self):
        return {
            'vet': VeterinarySupply.objects.filter(quantity__lte=F('reorder_level')).count(),
            'office': OfficeSupply.objects.filter(quantity__lte=F('reorder_level')).count()
        }

    def get_filtered_supplies(self, current_filter):
        queryset = VeterinarySupply.objects.all()
        if current_filter == 'low':
            return queryset.filter(quantity__lte=F('reorder_level'))
        elif current_filter == 'warning':
            return queryset.filter(
                quantity__gt=F('reorder_level'),
                quantity__lte=F('minimum_stock')
            )
        elif current_filter == 'adequate':
            return queryset.filter(quantity__gt=F('minimum_stock'))
        return queryset

    def get_cached_movements(self):
        """Get recent movements with caching"""
        cache_key = 'recent_inventory_movements'
        movements = cache.get(cache_key)
        
        if not movements:
            movements = list(InventoryMovement.objects.select_related(
                'content_type'
            ).order_by('-timestamp')[:10])
            cache.set(cache_key, movements, timeout=60*5)  # Cache for 5 minutes
        
        return movements

class InventoryMovementListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = InventoryMovement
    template_name = 'reports/movements.html'
    context_object_name = 'movements'
    paginate_by = 50

    def test_func(self):
        return self.request.user.is_staff

    def get_queryset(self):
        queryset = InventoryMovement.objects.all()
        
        # Filter by type (vet/office)
        item_type = self.request.GET.get('type')
        if item_type:
            queryset = queryset.filter(item_type=item_type)

        # Filter by action
        action = self.request.GET.get('action')
        if action:
            queryset = queryset.filter(action=action)

        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(
                timestamp__date__range=[start_date, end_date]
            )

        return queryset.order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_types'] = [
            ('vet', 'Veterinary Supplies'),
            ('office', 'Office Supplies')
        ]
        context['actions'] = [
            ('created', 'Added'),
            ('restocked', 'Restocked'),
            ('depleted', 'Depleted'),
            ('request_approved', 'Request Approved'),
            ('deleted', 'Deleted')
        ]
        return context

def export_report(request):
    if not request.user.is_staff:
        return HttpResponse('Unauthorized', status=401)

    report_type = request.GET.get('type', 'all')
    
    response = HttpResponse(content_type='text/csv')
    filename = f"inventory_{report_type}_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Item', 'Category', 'Type', 'Action', 'Previous Qty', 'New Qty', 'Unit'])
    
    queryset = InventoryMovement.objects.all().order_by('-timestamp')
    
    if report_type != 'all':
        queryset = queryset.filter(item_type=report_type)

    for movement in queryset:
        writer.writerow([
            movement.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            movement.item_name,
            movement.category,
            movement.item_type.title(),
            movement.action.title(),
            movement.previous_quantity or 'N/A',
            movement.quantity,
            movement.unit or 'units'
        ])
    
    return response