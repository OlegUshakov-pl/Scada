
from django.db import models
from django.utils import timezone

class Device(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название")
    ip = models.CharField(max_length=50, verbose_name="IP")
    protocol = models.CharField(max_length=20, choices=[('modbus','Modbus TCP'),('opcua','OPC UA'),('s7','Siemens S7')])

class Tag(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, verbose_name="Тэг (temp_01)")
    address = models.IntegerField(verbose_name="Адрес регистра")
    unit = models.CharField(max_length=20, blank=True, verbose_name="Ед. изм.")

class Rule(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название правила")
    condition = models.TextField(default="tags.get('pressure', 99) < 2.0", verbose_name="Условие (Python)")
    action = models.TextField(default="stop('pump_01')", verbose_name="Действие")
    is_active = models.BooleanField(default=True)

class Screen(models.Model):
    name = models.CharField(max_length=100)
    layout = models.JSONField(default=dict, verbose_name="JSON layout конструктора (legacy)")
    width = models.IntegerField(default=900, verbose_name="Ширина канваса")
    height = models.IntegerField(default=600, verbose_name="Высота канваса")
    # Виджеты конструктора (формат прототипа): [{id, type, x, y, w, h,
    # color, label, rotation, tag_id, device_id}, ...]. tag_id/device_id
    # могут быть None (непривязанный виджет, напр. label/труба).
    widgets = models.JSONField(default=list, verbose_name="Виджеты (JSON)")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

class Widget(models.Model):
    WIDGET_TYPES = [('number', 'Число'), ('chart', 'График'), ('indicator', 'Индикатор')]
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name='legacy_widgets')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES, default='number')
    row = models.IntegerField(default=0)
    col = models.IntegerField(default=0)
    label = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.label or self.tag.name} ({self.widget_type}) [{self.row},{self.col}]"

class ServiceToken(models.Model):
    """Сервисный токен для доступа к /api/* (logic_engine и др.).

    Задел на права: токен привязан к User, поэтому когда появятся
    per-object/per-model права, достаточно проверять request.api_user
    через стандартный user.has_perm(...) — владелец токена и его
    группы уже задают права.
    Хранится только sha256-хэш, сырой токен показывается один раз
    при создании (management-команда create_service_token).
    """
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="service_tokens",
        verbose_name="Владелец (пользователь)",
    )
    name = models.CharField(max_length=100, verbose_name="Название (напр. logic_engine)")
    key_hash = models.CharField(max_length=64, unique=True, verbose_name="SHA-256 хэш")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        state = "active" if self.is_active else "revoked"
        return f"{self.name} ({self.user.username}, {state})"
