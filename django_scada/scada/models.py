
from django.db import models

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
    layout = models.JSONField(default=dict, verbose_name="JSON layout конструктора")
