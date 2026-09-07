from django.urls import path

from . import views

urlpatterns = [
    path("api/rules/", views.api_rules, name="api-rules"),
    path("api/devices/<int:device_id>/tags/", views.api_device_tags, name="api-device-tags"),
    path("api/screens/<int:screen_id>/widgets/", views.api_screen_widgets, name="api-screen-widgets"),
    path("screens/<int:screen_id>/", views.dashboard, name="dashboard"),
]
