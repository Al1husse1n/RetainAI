from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("complaints/", views.complaints, name="complaints"),
    path("run-campaign/", views.stream_campaign, name="stream_campaign"),
    path("submit-complaint/", views.get_complaint, name="get_complaint"),
    path("stream-complaint/", views.stream_complaint, name="stream_complaint"),
]
