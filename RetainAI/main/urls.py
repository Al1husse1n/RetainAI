from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("run-campaign/", views.stream_campaign, name="stream_campaign"),
    path("submit-complaint/", views.get_complaint, name="get_complaint"),
]
