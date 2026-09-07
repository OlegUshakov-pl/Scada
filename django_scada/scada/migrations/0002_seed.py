# -*- coding: utf-8 -*-
"""Seed demo-данных: устройство + тэги + правила + экран с виджетами.

Идемпотентно (get_or_create / update_or_create) — можно катить поверх
существующей БД, дубликатов не будет.
"""
from django.db import migrations


def seed(apps, schema_editor):
    Device = apps.get_model("scada", "Device")
    Tag = apps.get_model("scada", "Tag")
    Rule = apps.get_model("scada", "Rule")
    Screen = apps.get_model("scada", "Screen")
    Widget = apps.get_model("scada", "Widget")

    device, _ = Device.objects.get_or_create(
        name="Насосная 1",
        defaults={"ip": "192.168.1.10", "protocol": "modbus"},
    )

    tags_spec = [
        ("pressure", 0, "bar"),
        ("temp_01", 1, "C"),
        ("pump_fb", 2, ""),
    ]
    tags = {}
    for name, address, unit in tags_spec:
        tag, _ = Tag.objects.get_or_create(
            device=device, name=name,
            defaults={"address": address, "unit": unit},
        )
        tags[name] = tag

    Rule.objects.update_or_create(
        name="Защита насоса по давлению",
        defaults={
            "condition": "tags.get('pressure', 99) < 2.0 and duration('pressure', '< 2.0') > 5",
            "action": "stop('pump_01'); alarm('Насос СТОП - давление <2 бар уже 5 сек')",
            "is_active": True,
        },
    )
    Rule.objects.update_or_create(
        name="Перегрев",
        defaults={
            "condition": "tags.get('temp_01', 0) > 90",
            "action": "alarm(f\"Перегрев! temp_01={tags['temp_01']}\")",
            "is_active": True,
        },
    )

    screen, _ = Screen.objects.get_or_create(
        name="Главный", defaults={"layout": {}},
    )
    widgets_spec = [
        ("pressure", "number", 0, 0, "Давление"),
        ("temp_01", "number", 0, 1, "Температура"),
        ("pump_fb", "indicator", 1, 0, "Насос (обратная связь)"),
    ]
    for tag_name, wtype, row, col, label in widgets_spec:
        Widget.objects.get_or_create(
            screen=screen, tag=tags[tag_name], widget_type=wtype,
            row=row, col=col,
            defaults={"label": label},
        )


def unseed(apps, schema_editor):
    Widget = apps.get_model("scada", "Widget")
    Screen = apps.get_model("scada", "Screen")
    Rule = apps.get_model("scada", "Rule")
    Tag = apps.get_model("scada", "Tag")
    Device = apps.get_model("scada", "Device")
    Widget.objects.filter(screen__name="Главный").delete()
    Screen.objects.filter(name="Главный").delete()
    Rule.objects.filter(name__in=["Защита насоса по давлению", "Перегрев"]).delete()
    Tag.objects.filter(device__name="Насосная 1").delete()
    Device.objects.filter(name="Насосная 1").delete()


class Migration(migrations.Migration):
    dependencies = [("scada", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
