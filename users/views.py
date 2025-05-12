from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.auth.decorators import login_required
from .forms import UserLoginForm, AdminLoginForm, CustomUserCreationForm
from .models import CustomUser

class CustomLoginView(LoginView):
    form_class = UserLoginForm
    template_name = 'users/login.html'
    
    def get_success_url(self):
        return '/'  # Always redirect to home

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_admin'] = False
        return context

class AdminLoginView(LoginView):
    form_class = AdminLoginForm
    template_name = 'users/admin_login.html'
    
    def get_success_url(self):
        return '/'  # Always redirect to home

    def form_valid(self, form):
        if not form.get_user().is_staff:
            form.add_error(None, "You don't have admin privileges.")
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_admin'] = True
        return context

class SignupView(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'users/signup.html'
    success_url = '/login/'

class CustomLogoutView(LogoutView):
    template_name = 'users/logout.html'
    next_page = 'home'  # Changed from 'login' to 'home'
    
    def get(self, request, *args, **kwargs):
        # Show confirmation page on GET request
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        # Process logout on POST request
        return super().post(request, *args, **kwargs)

def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
        
        # Add your token verification logic here
        user.is_verified = True
        user.save()
        
        messages.success(request, 'Your email has been verified!')
        return redirect('login')
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        messages.error(request, 'Invalid verification link.')
        return redirect('login')

@login_required
def profile_view(request):
    return render(request, 'users/profile.html', {
        'user': request.user
    })