from django.urls import path

from .views import BootstrapView, ChartCountsView, DetailView, GenerateView, OriginalView, RowsView, ServiceView, UploadView
from .admin_views import FieldChoicesView, FieldChoiceView, FieldLabelView, ManagedRowsView, ManagedRowView
from .understanding_views import UnderstandingView
from .booking_views import (AvailabilityView, BookingStatsView, BookingView, BookingsView, ResourceFacetsView, ResourceView, ResourcesView, ScopesView,
                            SlotView, SlotsView)
from .inquiry_views import InquiriesView, InquiryView, InquiryStatsView
from .notice_views import NoticesView, NoticeView

urlpatterns = [
    path("session/", BootstrapView.as_view()),
    path("uploads/", UploadView.as_view()),
    path("uploads/<uuid:pk>/", DetailView.as_view()),
    path("uploads/<uuid:pk>/service/", ServiceView.as_view()),
    path("uploads/<uuid:pk>/generate/", GenerateView.as_view()),
    path("uploads/<uuid:pk>/understanding/", UnderstandingView.as_view()),
    path("uploads/<uuid:pk>/resources/", ResourcesView.as_view()),
    path("uploads/<uuid:pk>/resources/facets/", ResourceFacetsView.as_view()),
    path("uploads/<uuid:pk>/resources/<uuid:resource_id>/", ResourceView.as_view()),
    path("uploads/<uuid:pk>/slots/", SlotsView.as_view()),
    path("uploads/<uuid:pk>/slots/<uuid:slot_id>/", SlotView.as_view()),
    path("uploads/<uuid:pk>/bookings/", BookingsView.as_view()),
    path("uploads/<uuid:pk>/bookings/stats/", BookingStatsView.as_view()),
    path("uploads/<uuid:pk>/bookings/availability/", AvailabilityView.as_view()),
    path("uploads/<uuid:pk>/bookings/scopes/", ScopesView.as_view()),
    path("uploads/<uuid:pk>/bookings/<uuid:booking_id>/", BookingView.as_view()),
    path("uploads/<uuid:pk>/inquiries/", InquiriesView.as_view()),
    path("uploads/<uuid:pk>/inquiries/stats/", InquiryStatsView.as_view()),
    path("uploads/<uuid:pk>/inquiries/<uuid:inquiry_id>/", InquiryView.as_view()),
    path("uploads/<uuid:pk>/notices/", NoticesView.as_view()),
    path("uploads/<uuid:pk>/notices/<uuid:notice_id>/", NoticeView.as_view()),
    path("uploads/<uuid:pk>/managed-rows/", ManagedRowsView.as_view()),
    path("uploads/<uuid:pk>/managed-rows/<uuid:row_id>/", ManagedRowView.as_view()),
    path("uploads/<uuid:pk>/choices/", FieldChoicesView.as_view()),
    path("uploads/<uuid:pk>/choices/<uuid:choice_id>/", FieldChoiceView.as_view()),
    path("uploads/<uuid:pk>/fields/<int:column>/", FieldLabelView.as_view()),
    path("uploads/<uuid:pk>/original/", OriginalView.as_view()),
    path("uploads/<uuid:pk>/rows/", RowsView.as_view()),
    path("uploads/<uuid:pk>/chart-counts/", ChartCountsView.as_view()),
]
