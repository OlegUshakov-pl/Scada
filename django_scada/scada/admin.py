from django.contrib import admin
from .models import Device, Tag, Rule, Screen
admin.site.register(Device)
admin.site.register(Tag)
admin.site.register(Rule)
admin.site.register(Screen)
