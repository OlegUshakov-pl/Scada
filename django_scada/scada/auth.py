# -*- coding: utf-8 -*-
"""Минимальная авторизация без новых зависимостей.

Схема (с заделом на будущие права пользователей):
- API принимает либо Django-сессию (залогиненный пользователь),
  либо Bearer-токен сервиса из заголовка Authorization.
- Токен привязан к auth.User (ServiceToken.user): когда введём
  права, проверки сведутся к request.api_user.has_perm(...),
 standard Groups/Permissions заработают и для сервисов.
"""
import hashlib
import secrets
from functools import wraps

from django.http import JsonResponse

TOKEN_HEADER_PREFIX = "Bearer "
TOKEN_BYTES = 32


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token():
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, hash_token(raw)


def get_token_user(request):
    """Вернуть User по Bearer-токену или None. Импорт модели — внутри,
    чтобы не тянуть apps раньше готовности."""
    from .models import ServiceToken

    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith(TOKEN_HEADER_PREFIX):
        return None
    raw = auth[len(TOKEN_HEADER_PREFIX):].strip()
    if not raw:
        return None
    try:
        token = ServiceToken.objects.select_related("user").get(
            key_hash=hash_token(raw), is_active=True,
        )
    except ServiceToken.DoesNotExist:
        return None
    if not token.user.is_active:
        return None
    return token.user


def api_auth_required(view):
    """Доступ: залогиненный пользователь (сессия) ИЛИ активный Bearer-токен.

    request.api_user — итоговый User. Будущие права проверять так:
        if not request.api_user.has_perm("scada.view_rule"): -> 403
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = None
        if getattr(request.user, "is_authenticated", False):
            user = request.user
        else:
            user = get_token_user(request)
        if user is None or not user.is_active:
            return JsonResponse(
                {"detail": "Authentication required (session or Bearer token)."},
                status=401,
            )
        request.api_user = user
        return view(request, *args, **kwargs)
    return wrapper
