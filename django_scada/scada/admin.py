from django.contrib import admin
from .models import Device, ServiceToken, Tag, Rule, Screen, Widget

class TagInline(admin.TabularInline):
    model = Tag
    extra = 1

class WidgetInline(admin.TabularInline):
    model = Widget
    extra = 1

class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip', 'protocol')
    inlines = [TagInline]

class ScreenAdmin(admin.ModelAdmin):
    list_display = ('name', 'width', 'height', 'updated_at')
    inlines = [WidgetInline]

admin.site.register(Device, DeviceAdmin)
admin.site.register(Tag)
admin.site.register(Rule)
admin.site.register(Screen, ScreenAdmin)
admin.site.register(Widget)


@admin.register(ServiceToken)
class ServiceTokenAdmin(admin.ModelAdmin):
    # Сырой токен нигде не хранится — только хэш, поэтому создать можно
    # лишь через: python manage.py create_service_token --user <name>
    list_display = ("name", "user", "is_active", "created_at")
    list_filter = ("is_active",)
    readonly_fields = ("key_hash", "created_at")
    actions = ["revoke"]

    @admin.action(description="Revoke selected tokens")
    def revoke(self, request, queryset):
        queryset.update(is_active=False)
