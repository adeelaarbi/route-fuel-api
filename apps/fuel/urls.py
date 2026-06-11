from django.urls import path

from apps.fuel.views import FuelOptimizeAPIView

urlpatterns = [
    path("trips/optimize-fuel/", FuelOptimizeAPIView.as_view(), name="optimize-fuel"),
]
