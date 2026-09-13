from django.contrib.auth import login
from django.db import transaction
from django.shortcuts import redirect, render
from billing.models import BillingAccount
from core.models import Membership, Workspace
from .forms import SignupForm


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            workspace = Workspace.objects.create(name=f'{user.username} workspace')
            Membership.objects.create(workspace=workspace, user=user)
            BillingAccount.objects.create(workspace=workspace)
        login(request, user)
        return redirect('dashboard')
    return render(request, 'form.html', {'form': form, 'title': 'Create your account'})
