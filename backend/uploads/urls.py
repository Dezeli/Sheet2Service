from django.urls import path

from .views import BootstrapView, ChartCountsView, DetailView, InferenceView, OriginalView, RowsView, ServiceView, UploadView
from .admin_views import FieldChoicesView, FieldChoiceView, ManagedRowsView, ManagedRowView
from .workflow_views import CustomFlowPreviewView, CustomFlowRunView, WorkflowView
from .request_views import ServiceRequestsView, ServiceRequestView, ServiceRequestStatsView

urlpatterns = [
    path("session/", BootstrapView.as_view()),
    path("uploads/", UploadView.as_view()),
    path("uploads/<uuid:pk>/", DetailView.as_view()),
    path("uploads/<uuid:pk>/service/", ServiceView.as_view()),
    path("uploads/<uuid:pk>/workflow/", WorkflowView.as_view()),
    path("uploads/<uuid:pk>/workflow/custom-preview/", CustomFlowPreviewView.as_view()),
    path("uploads/<uuid:pk>/workflow/custom-run/", CustomFlowRunView.as_view()),
    path("uploads/<uuid:pk>/service-requests/", ServiceRequestsView.as_view()),
    path("uploads/<uuid:pk>/service-requests/stats/", ServiceRequestStatsView.as_view()),
    path("uploads/<uuid:pk>/service-requests/<uuid:request_id>/", ServiceRequestView.as_view()),
    path("uploads/<uuid:pk>/managed-rows/", ManagedRowsView.as_view()),
    path("uploads/<uuid:pk>/managed-rows/<uuid:row_id>/", ManagedRowView.as_view()),
    path("uploads/<uuid:pk>/choices/", FieldChoicesView.as_view()),
    path("uploads/<uuid:pk>/choices/<uuid:choice_id>/", FieldChoiceView.as_view()),
    path("uploads/<uuid:pk>/inference/", InferenceView.as_view()),
    path("uploads/<uuid:pk>/original/", OriginalView.as_view()),
    path("uploads/<uuid:pk>/rows/", RowsView.as_view()),
    path("uploads/<uuid:pk>/chart-counts/", ChartCountsView.as_view()),
]
