from django.urls import path

from . import views

urlpatterns = [
    path("api/rules/", views.api_rules, name="api-rules"),
    path("api/devices/", views.api_devices, name="api-devices"),
    path("api/tags/", views.api_tags, name="api-tags"),
    path("api/devices/<int:device_id>/tags/", views.api_device_tags, name="api-device-tags"),
    path("api/screens/", views.api_screens, name="api-screens"),
    path("api/screens/<int:screen_id>/", views.api_screen_detail, name="api-screen-detail"),
    path("api/screens/<int:screen_id>/widgets/", views.api_screen_widgets, name="api-screen-widgets"),
    path("screens/<int:screen_id>/", views.dashboard, name="dashboard"),
    path("screens/<int:screen_id>/edit/", views.constructor_editor, name="constructor-editor"),
]
