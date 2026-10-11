from django.urls import path

from .views import BootstrapView, ChartCountsView, DetailView, InferenceView, OriginalView, RowsView, ServiceView, UploadView
from .admin_views import FieldChoicesView, FieldChoiceView, FieldLabelView, ManagedRowsView, ManagedRowView
from .workflow_views import CustomFlowPreviewView, CustomFlowRunView, WorkflowView
from .request_views import ServiceRequestsView, ServiceRequestView, ServiceRequestStatsView
from .inquiry_views import InquiriesView, InquiryView, InquiryStatsView
from .reservation_views import ReservationSlotsView, ReservationSlotView, ReservationsView, ReservationView
from .notice_views import NoticesView, NoticeView
from .rental_views import RentalStocksView, RentalStockView, RentalsView, RentalView
from .quote_views import QuoteRequestsView, QuoteRequestView

urlpatterns = [
    path("session/", BootstrapView.as_view()),
    path("uploads/", UploadView.as_view()),
    path("uploads/<uuid:pk>/", DetailView.as_view()),
    path("uploads/<uuid:pk>/service/", ServiceView.as_view()),
    path("uploads/<uuid:pk>/workflow/", WorkflowView.as_view()),
    path("uploads/<uuid:pk>/workflow/custom-preview/", CustomFlowPreviewView.as_view()),
    path("uploads/<uuid:pk>/workflow/custom-run/", CustomFlowRunView.as_view()),
    path("uploads/<uuid:pk>/service-requests/", ServiceRequestsView.as_view()),
    path("uploads/<uuid:pk>/inquiries/", InquiriesView.as_view()),
    path("uploads/<uuid:pk>/notices/", NoticesView.as_view()),
    path("uploads/<uuid:pk>/quote-requests/", QuoteRequestsView.as_view()),
    path("uploads/<uuid:pk>/quote-requests/<uuid:quote_id>/", QuoteRequestView.as_view()),
    path("uploads/<uuid:pk>/rental-stocks/", RentalStocksView.as_view()),
    path("uploads/<uuid:pk>/rental-stocks/<uuid:stock_id>/", RentalStockView.as_view()),
    path("uploads/<uuid:pk>/rentals/", RentalsView.as_view()),
    path("uploads/<uuid:pk>/rentals/<uuid:rental_id>/", RentalView.as_view()),
    path("uploads/<uuid:pk>/notices/<uuid:notice_id>/", NoticeView.as_view()),
    path("uploads/<uuid:pk>/reservation-slots/", ReservationSlotsView.as_view()),
    path("uploads/<uuid:pk>/reservation-slots/<uuid:slot_id>/", ReservationSlotView.as_view()),
    path("uploads/<uuid:pk>/reservations/", ReservationsView.as_view()),
    path("uploads/<uuid:pk>/reservations/<uuid:reservation_id>/", ReservationView.as_view()),
    path("uploads/<uuid:pk>/inquiries/stats/", InquiryStatsView.as_view()),
    path("uploads/<uuid:pk>/inquiries/<uuid:inquiry_id>/", InquiryView.as_view()),
    path("uploads/<uuid:pk>/service-requests/stats/", ServiceRequestStatsView.as_view()),
    path("uploads/<uuid:pk>/service-requests/<uuid:request_id>/", ServiceRequestView.as_view()),
    path("uploads/<uuid:pk>/managed-rows/", ManagedRowsView.as_view()),
    path("uploads/<uuid:pk>/managed-rows/<uuid:row_id>/", ManagedRowView.as_view()),
    path("uploads/<uuid:pk>/choices/", FieldChoicesView.as_view()),
    path("uploads/<uuid:pk>/fields/<int:column>/", FieldLabelView.as_view()),
    path("uploads/<uuid:pk>/choices/<uuid:choice_id>/", FieldChoiceView.as_view()),
    path("uploads/<uuid:pk>/inference/", InferenceView.as_view()),
    path("uploads/<uuid:pk>/original/", OriginalView.as_view()),
    path("uploads/<uuid:pk>/rows/", RowsView.as_view()),
    path("uploads/<uuid:pk>/chart-counts/", ChartCountsView.as_view()),
]
