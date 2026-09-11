import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt

from .auth import api_auth_required
from .models import Device, Rule, Screen, Tag


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
        screen.legacy_widgets.select_related("tag").all().order_by("row", "col")
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


def _screen_to_dict(screen):
    return {
        "id": screen.id,
        "name": screen.name,
        "width": screen.width,
        "height": screen.height,
        "widgets": screen.widgets or [],
        "created_at": screen.created_at.isoformat() if screen.created_at else None,
        "updated_at": screen.updated_at.isoformat() if screen.updated_at else None,
    }


def _validate_widgets(widgets):
    """Проверить массив виджетов прототипа. Возвращает (cleaned, error)."""
    if not isinstance(widgets, list):
        return None, "widgets must be a list"
    tag_ids = {w.get("tag_id") for w in widgets if isinstance(w, dict) and w.get("tag_id") is not None}
    dev_ids = {w.get("device_id") for w in widgets if isinstance(w, dict) and w.get("device_id") is not None}
    existing_tags = set(Tag.objects.filter(pk__in=tag_ids).values_list("pk", flat=True)) if tag_ids else set()
    existing_devs = set(Device.objects.filter(pk__in=dev_ids).values_list("pk", flat=True)) if dev_ids else set()
    cleaned = []
    for w in widgets:
        if not isinstance(w, dict):
            return None, "each widget must be an object"
        tag_id = w.get("tag_id")
        dev_id = w.get("device_id")
        if tag_id is not None and tag_id not in existing_tags:
            return None, f"unknown tag_id={tag_id}"
        if dev_id is not None and dev_id not in existing_devs:
            return None, f"unknown device_id={dev_id}"
        cleaned.append({
            "id": str(w.get("id", "")),
            "type": str(w.get("type", "")),
            "x": w.get("x", 0), "y": w.get("y", 0),
            "w": w.get("w", 56), "h": w.get("h", 56),
            "color": w.get("color", "#888888"),
            "label": w.get("label", ""),
            "rotation": w.get("rotation", 0),
            "tag_id": tag_id, "device_id": dev_id,
        })
    return cleaned, None


def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}"), None
    except (ValueError, UnicodeDecodeError):
        return None, "invalid JSON"


@csrf_exempt
@api_auth_required
def api_screens(request):
    """GET /api/screens/ — список; POST /api/screens/ — создание."""
    if request.method == "GET":
        screens = Screen.objects.all().order_by("id")
        return JsonResponse([_screen_to_dict(s) for s in screens], safe=False)
    if request.method == "POST":
        data, err = _parse_json_body(request)
        if err:
            return JsonResponse({"detail": err}, status=400)
        widgets, werr = _validate_widgets(data.get("widgets", []))
        if werr:
            return JsonResponse({"detail": werr}, status=400)
        screen = Screen.objects.create(
            name=data.get("name", "Новый экран"),
            width=int(data.get("width", 900)),
            height=int(data.get("height", 600)),
            widgets=widgets,
        )
        return JsonResponse(_screen_to_dict(screen), status=201)
    return JsonResponse({"detail": "method not allowed"}, status=405)


@csrf_exempt
@api_auth_required
def api_screen_detail(request, screen_id):
    """GET /api/screens/<id>/; PATCH — частичное обновление (имя/размер/widgets)."""
    screen = get_object_or_404(Screen, pk=screen_id)
    if request.method == "GET":
        return JsonResponse(_screen_to_dict(screen))
    if request.method in ("PATCH", "PUT"):
        data, err = _parse_json_body(request)
        if err:
            return JsonResponse({"detail": err}, status=400)
        if "name" in data:
            screen.name = str(data["name"])[:100]
        if "width" in data:
            screen.width = int(data["width"])
        if "height" in data:
            screen.height = int(data["height"])
        if "widgets" in data:
            widgets, werr = _validate_widgets(data["widgets"])
            if werr:
                return JsonResponse({"detail": werr}, status=400)
            screen.widgets = widgets
        screen.save()
        return JsonResponse(_screen_to_dict(screen))
    return JsonResponse({"detail": "method not allowed"}, status=405)


@api_auth_required
def api_devices(request):
    """GET /api/devices/ — устройства для панели свойств конструктора."""
    devices = Device.objects.all().order_by("id").values("id", "name", "ip", "protocol")
    return JsonResponse(list(devices), safe=False)


@api_auth_required
def api_tags(request):
    """GET /api/tags/ (+?device_id=) — тэги для панели свойств."""
    qs = Tag.objects.select_related("device").all().order_by("id")
    device_id = request.GET.get("device_id")
    if device_id:
        qs = qs.filter(device_id=device_id)
    data = [{"id": t.id, "device_id": t.device_id, "device": t.device.name,
             "name": t.name, "address": t.address, "unit": t.unit} for t in qs]
    return JsonResponse(data, safe=False)
