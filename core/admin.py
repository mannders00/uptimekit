from django.contrib import admin

from .models import Workspace, Membership, Heartbeat

admin.site.register([Workspace, Membership, Heartbeat])
