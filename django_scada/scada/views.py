from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .auth import api_auth_required
from .models import Device, Rule, Screen


@api_auth_required
def api_rules(request):
    """GET /api/rules/ — активные Rule для logic_engine."""
    rules = Rule.objects.filter(is_active=True).values("name", "condition", "action")
    return JsonResponse(list(rules), safe=False)


@api_auth_required
def api_device_tags(request, device_id):
    """GET /api/devices/<id>/tags/ — карта регистров для C3-драйвера."""
    device = get_object_or_404(Device, pk=device_id)
    tags = device.tag_set.all().order_by("address").values("name", "address", "unit")
    return JsonResponse(list(tags), safe=False)


@api_auth_required
def api_screen_widgets(request, screen_id):
    """GET /api/screens/<id>/widgets/ — виджеты экрана для дашборда."""
    screen = get_object_or_404(Screen, pk=screen_id)
    widgets = (
        screen.widgets.select_related("tag").all().order_by("row", "col")
    )
    data = [
        {
            "id": w.id,
            "tag": w.tag.name,
            "unit": w.tag.unit,
            "widget_type": w.widget_type,
            "row": w.row,
            "col": w.col,
            "label": w.label or w.tag.name,
        }
        for w in widgets
    ]
    return JsonResponse(data, safe=False)


@login_required
def dashboard(request, screen_id):
    """Простой HTML-дашборд: grid по row/col + WS к FastAPI."""
    screen = get_object_or_404(Screen, pk=screen_id)
    return render(request, "scada/dashboard.html", {"screen": screen})
