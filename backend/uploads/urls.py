from django.urls import path

from .views import BootstrapView, ChartCountsView, DetailView, InferenceView, OriginalView, RowsView, UploadView

urlpatterns = [
    path("session/", BootstrapView.as_view()),
    path("uploads/", UploadView.as_view()),
    path("uploads/<uuid:pk>/", DetailView.as_view()),
    path("uploads/<uuid:pk>/inference/", InferenceView.as_view()),
    path("uploads/<uuid:pk>/original/", OriginalView.as_view()),
    path("uploads/<uuid:pk>/rows/", RowsView.as_view()),
    path("uploads/<uuid:pk>/chart-counts/", ChartCountsView.as_view()),
]
