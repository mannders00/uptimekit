from django.shortcuts import get_object_or_404
from .models import Workspace


def workspace_for(user, workspace_id, owner=False):
    query = Workspace.objects.filter(memberships__user=user)
    if owner:
        query = query.filter(memberships__user=user, memberships__role='owner')
    return get_object_or_404(query, pk=workspace_id)
