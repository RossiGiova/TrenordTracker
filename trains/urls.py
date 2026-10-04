from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("linea/<str:code>/", views.line_detail, name="line_detail"),
    path("treno/<str:number>/", views.train_detail, name="train_detail"),
    path("api/summary/", views.api_summary, name="api_summary"),
    path("api/runs/", views.api_runs, name="api_runs"),
    path("api/runs/<int:pk>/", views.api_run_detail, name="api_run_detail"),
    path("api/lines/<str:code>/live/", views.api_line_live, name="api_line_live"),
    path("api/lines/<str:code>/stats/", views.api_line_stats, name="api_line_stats"),
]
