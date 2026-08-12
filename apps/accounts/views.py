from django.contrib.auth.views import LoginView, LogoutView

from apps.accounts.forms import EmailAuthenticationForm


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class KusanyaLogoutView(LogoutView):
    next_page = "accounts:login"
