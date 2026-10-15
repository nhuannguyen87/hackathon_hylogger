"""URL -> view map. Adding an endpoint? Add the function in views.py, then a line here."""
from django.urls import path

from . import views

urlpatterns = [
    path("holes/", views.hole_list),
    path("holes/<str:hole_id>/", views.hole_detail),
    path("holes/<str:hole_id>/measurements/", views.hole_measurements),
    path("holes/<str:hole_id>/trays/", views.hole_trays),
    path("holes/<str:hole_id>/minerals/", views.hole_minerals),
    path("holes/<str:hole_id>/assays/", views.hole_assays),
    path("holes/<str:hole_id>/geology/", views.hole_geology),
    path("holes/<str:hole_id>/export.csv", views.hole_export),
    path("holes/<str:hole_id>/anomalies/", views.hole_anomalies),
    path("holes/<str:hole_id>/trace/", views.hole_trace),
    path("holes/<str:hole_id>/nearby/", views.hole_nearby),
    path("holes/<str:hole_id>/spectral-sample/", views.hole_spectral_sample),
    path("holes/<str:hole_id>/core-strip/", views.hole_core_strip),
    path("mineral-logs/", views.mineral_logs),
    path("minerals/", views.mineral_list),
    path("qgis/holes.geojson", views.qgis_holes),
    path("qgis/intervals.geojson", views.qgis_intervals),
    path("qgis/assays.geojson", views.qgis_assays),
    path("minerals/richness/", views.mineral_richness),
    path("vocab/", views.vocab),
    path("distance/", views.distance),
    path("stats/", views.stats),
]
