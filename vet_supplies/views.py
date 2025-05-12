from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages  
from django.contrib.contenttypes.models import ContentType
from django.db.models import F, Q  # Add this import
from django.urls import reverse_lazy
from django.utils import timezone
from .models import VeterinarySupply, VeterinarySupplyRequest, VeterinarySupplyCategory
from .forms import VeterinarySupplyForm, RequestForm, BulkSupplyUploadForm, RequestItemFormSet, BulkRequestForm  # Add this import
from reports.models import InventoryMovement
import csv
import io
from django.shortcuts import redirect
from django.core.exceptions import ValidationError

class SupplyListView(LoginRequiredMixin, ListView):
    model = VeterinarySupply
    template_name = 'vet_supplies/list.html'
    context_object_name = 'supplies'
    paginate_by = 10  # Set pagination size

    def get_queryset(self):
        queryset = VeterinarySupply.objects.select_related('category').order_by('name')
        
        # Filter by stock status
        stock_status = self.request.GET.get('stock_status')
        if stock_status == 'low':
            queryset = queryset.filter(quantity__lte=F('reorder_level'))
        elif stock_status == 'adequate':
            queryset = queryset.filter(quantity__gt=F('reorder_level'))
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context['low_stock_count'] = VeterinarySupply.objects.filter(
            quantity__lte=F('reorder_level')  # Changed from critical_stock
        ).count()
        context['expiring_count'] = VeterinarySupply.objects.filter(
            expiration_date__gt=today,
            expiration_date__lte=today + timezone.timedelta(days=30)
        ).count()
        context['is_staff'] = self.request.user.is_staff
        context['categories'] = VeterinarySupplyCategory.objects.all()
        return context

class SupplyCreateView(LoginRequiredMixin, CreateView):
    model = VeterinarySupply
    form_class = VeterinarySupplyForm
    template_name = 'vet_supplies/form.html'
    success_url = '/vet-supplies/'

    def form_valid(self, form):
        response = super().form_valid(form)
        # Log the initial creation with initial stock
        if form.cleaned_data['quantity'] > 0:
            InventoryMovement.objects.create(
                content_type=ContentType.objects.get_for_model(self.object),
                object_id=self.object.id,
                action='created',
                quantity=self.object.quantity,
                previous_quantity=0,
                item_type='vet',
                item_name=self.object.name,
                category=self.object.category.name,
                unit=self.object.unit
            )
        return response

class SupplyUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = VeterinarySupply
    form_class = VeterinarySupplyForm
    template_name = 'vet_supplies/form.html'
    success_url = reverse_lazy('vet-supply-list')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        # Store current values before save
        self.object = form.instance
        old_instance = VeterinarySupply.objects.get(pk=self.object.pk)
        
        # Save new values
        response = super().form_valid(form)
        
        # Create movement record if non-quantity fields changed
        if any(getattr(self.object, field) != getattr(old_instance, field) 
               for field in ['name', 'category', 'unit', 'notes', 'expiration_date']):
            InventoryMovement.objects.create(
                content_type=ContentType.objects.get_for_model(self.object),
                object_id=self.object.id,
                action='updated',
                quantity=self.object.quantity,
                previous_quantity=old_instance.quantity,
                item_type='vet',
                item_name=self.object.name,
                category=self.object.category.name,
                unit=self.object.unit
            )
        
        messages.success(self.request, f'Supply "{form.instance.name}" has been updated.')
        return response

class SupplyDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = VeterinarySupply
    template_name = 'vet_supplies/confirm_delete.html'
    success_url = reverse_lazy('supply-list')
    
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

class RequestCreateView(LoginRequiredMixin, CreateView):
    model = VeterinarySupplyRequest  
    template_name = 'vet_supplies/request_form.html'
    form_class = BulkRequestForm
    success_url = reverse_lazy('vet-request-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('instance', None)  # Remove instance since BulkRequestForm is not a ModelForm
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supplies'] = VeterinarySupply.objects.all().select_related('category', 'unit')
        return context

    def form_valid(self, form):
        items = form.cleaned_data.get('items', [])
        if not items:
            messages.error(self.request, 'Must select at least one item')
            return self.form_invalid(form)
        
        # Calculate total quantity for main request
        total_quantity = sum(item['quantity'] for item in items)
        
        # Create main request
        request = VeterinarySupplyRequest.objects.create(
            requester=self.request.user,
            purpose=form.cleaned_data['purpose'],
            is_bulk=True,
            quantity=total_quantity,  # Add total quantity
            supply=VeterinarySupply.objects.get(id=items[0]['id'])  # Use first item as main supply
        )
        
        # Create request items
        for item in items:
            try:
                supply = VeterinarySupply.objects.get(id=item['id'])
                RequestItem.objects.create(
                    request=request,
                    supply=supply,
                    quantity=item['quantity']
                )
            except VeterinarySupply.DoesNotExist:
                continue
        
        messages.success(self.request, 'Request submitted successfully.')
        return redirect(self.success_url)

class RequestDetailView(LoginRequiredMixin, DetailView):
    model = VeterinarySupplyRequest
    template_name = 'vet_supplies/request_detail.html'
    context_object_name = 'request'

class RequestListView(LoginRequiredMixin, ListView):
    model = VeterinarySupplyRequest
    template_name = 'vet_supplies/request_list.html'
    context_object_name = 'requests'
    paginate_by = 20

    def get_queryset(self):
        return VeterinarySupplyRequest.objects.select_related('supply', 'requester').order_by('-request_date')

class RequestUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = VeterinarySupplyRequest
    fields = ['status', 'approved_by']
    template_name = 'vet_supplies/request_update.html'
    success_url = reverse_lazy('vet-request-list')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        old_status = self.get_object().status
        new_status = form.cleaned_data['status']
        supply = form.instance.supply
        requested_qty = form.instance.quantity
        
        # Create movement record for status change
        if old_status != new_status:
            action = 'request_approved' if new_status == 'approved' else 'request_rejected'
            InventoryMovement.objects.create(
                content_type=ContentType.objects.get_for_model(supply),
                object_id=supply.id,
                action=action,
                quantity=requested_qty,
                previous_quantity=supply.quantity,
                item_type='vet',
                item_name=supply.name,
                category=supply.category.name,
                unit=supply.unit
            )

            if new_status == 'approved':
                if supply.quantity < requested_qty:
                    messages.error(self.request, f'Insufficient stock. Only {supply.quantity} {supply.unit} available.')
                    return self.form_invalid(form)

                supply.quantity -= requested_qty
                supply.save()
                form.instance.approval_date = timezone.now()
                form.instance.approved_by = self.request.user
                
                messages.success(self.request, f'Request approved and {requested_qty} {supply.unit} deducted from inventory.')

        return super().form_valid(form)

    def get_queryset(self):
        return super().get_queryset().select_related(
            'supply', 'requester'
        ).prefetch_related(
            'items__supply__category',
            'items__supply__unit'
        )

class CategoryCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = VeterinarySupplyCategory
    fields = ['name', 'description']
    template_name = 'vet_supplies/category_form.html'
    success_url = '/vet-supplies/'

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        messages.success(self.request, f'Category "{form.instance.name}" has been created.')
        return super().form_valid(form)

class BulkSupplyUploadView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = 'vet_supplies/bulk_upload.html'
    form_class = BulkSupplyUploadForm
    success_url = reverse_lazy('vet-supply-list')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        csv_file = form.cleaned_data['file']
        decoded_file = csv_file.read().decode('utf-8')
        csv_data = csv.DictReader(io.StringIO(decoded_file))
        
        success_count = 0
        error_count = 0
        
        for row in csv_data:
            try:
                category, _ = VeterinarySupplyCategory.objects.get_or_create(
                    name=row['category']
                )
                
                VeterinarySupply.objects.create(
                    name=row['name'],
                    category=category,
                    quantity=int(row['quantity']),
                    unit=row['unit'],
                    expiration_date=row['expiration_date'],
                    notes=row.get('notes', '')
                )
                success_count += 1
            except Exception as e:
                error_count += 1
                continue
        
        messages.success(self.request, 
            f'Successfully added {success_count} items. Failed: {error_count}')
        return super().form_valid(form)

class LowStockListView(LoginRequiredMixin, ListView):
    model = VeterinarySupply
    template_name = 'vet_supplies/list.html'
    context_object_name = 'supplies'

    def get_queryset(self):
        return VeterinarySupply.objects.filter(quantity__lte=F('reorder_level'))  # Changed from critical_stock

class ExpiringListView(LoginRequiredMixin, ListView):
    model = VeterinarySupply
    template_name = 'vet_supplies/list.html'
    context_object_name = 'supplies'

    def get_queryset(self):
        today = timezone.now().date()
        thirty_days = today + timezone.timedelta(days=30)
        return VeterinarySupply.objects.filter(
            expiration_date__gt=today,
            expiration_date__lte=thirty_days
        )