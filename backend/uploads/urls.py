from django.urls import path

from .views import BootstrapView, DetailView, InferenceView, OriginalView, UploadView

urlpatterns = [
    path("session/", BootstrapView.as_view()),
    path("uploads/", UploadView.as_view()),
    path("uploads/<uuid:pk>/", DetailView.as_view()),
    path("uploads/<uuid:pk>/inference/", InferenceView.as_view()),
    path("uploads/<uuid:pk>/original/", OriginalView.as_view()),
]
