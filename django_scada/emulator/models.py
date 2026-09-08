from django.core.exceptions import ValidationError
from django.db import models


class SimulatorDevice(models.Model):
    """Виртуальный генератор показаний для реального Device/Tag.

    Отдельная таблица, НЕ расширяет Device. Значение НИКОГДА не пишется
    в БД напрямую — публикуется тем же путём, что и данные реальных
    драйверов: POST /ingest FastAPI -> Redis HSET latest_tags
    (см. emulator.sender.publish). Там его подбирают Logic Engine и WS.
    """

    SIGNAL_TYPES = [
        ("temperature", "Температура"),
        ("pressure", "Давление"),
        ("digital_input", "Дискретный вход"),
        ("motor", "Двигатель"),
    ]
    MODES = [
        ("constant", "Постоянное"),
        ("random", "Случайное"),
        ("sine", "Синусоида"),
        ("ramp", "Пила (ramp)"),
        ("cycle", "Цикл 0/1 (cycle)"),
    ]

    device = models.ForeignKey(
        "scada.Device",
        on_delete=models.CASCADE,
        related_name="simulators",
        verbose_name="Реальное устройство",
        help_text="Показания какого устройства эмулируются. Источник правды для карты регистров.",
    )
    # FK(Device) по ТЗ недостаточно: ключ в latest_tags — это имя ТЭГА,
    # а у одного Device их несколько. tag указывает точный ключ публикации.
    tag = models.ForeignKey(
        "scada.Tag",
        on_delete=models.CASCADE,
        related_name="simulators",
        verbose_name="Тэг",
        help_text="В какой тэг публиковать (ключ в latest_tags = tag.name).",
    )
    signal_type = models.CharField(max_length=20, choices=SIGNAL_TYPES, verbose_name="Тип сигнала")
    mode = models.CharField(max_length=20, choices=MODES, verbose_name="Режим генерации")
    min_value = models.FloatField(verbose_name="Минимум диапазона")
    max_value = models.FloatField(verbose_name="Максимум диапазона")
    period = models.FloatField(
        default=60, verbose_name="Период, сек (sine/ramp/cycle)",
        help_text="Для constant/random не используется.",
    )
    update_interval = models.FloatField(verbose_name="Интервал генерации, сек")
    enabled = models.BooleanField(default=True, verbose_name="Включён")

    class Meta:
        verbose_name = "Симулятор"
        verbose_name_plural = "Симуляторы"

    def __str__(self):
        state = "on" if self.enabled else "off"
        return f"{self.tag.name} [{self.mode}] ({state})"

    def clean(self):
        super().clean()
        if self.tag_id and self.device_id and self.tag.device_id != self.device_id:
            raise ValidationError(
                {"tag": "Тэг должен принадлежать выбранному устройству."}
            )
        if self.min_value > self.max_value:
            raise ValidationError("min_value не может быть больше max_value.")
        if self.update_interval is not None and self.update_interval <= 0:
            raise ValidationError({"update_interval": "Должен быть > 0."})
        if self.mode in ("sine", "ramp", "cycle") and (not self.period or self.period <= 0):
            raise ValidationError({"period": "Для sine/ramp/cycle период должен быть > 0."})
