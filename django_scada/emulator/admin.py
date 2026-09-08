from django.contrib import admin

from .models import SimulatorDevice


@admin.register(SimulatorDevice)
class SimulatorDeviceAdmin(admin.ModelAdmin):
    list_display = ("tag", "device", "signal_type", "mode", "update_interval", "enabled")
    list_filter = ("signal_type", "mode", "enabled")
    list_editable = ("enabled",)
