# -*- coding: utf-8 -*-


from django.contrib import admin
from .models import NotifAuth, AuthToken, NotifData, NotifURL, ElevatorInfo

# Register your models here.

admin.site.register(NotifAuth)
admin.site.register(AuthToken)
admin.site.register(NotifData)
admin.site.register(NotifURL)
admin.site.register(ElevatorInfo)
