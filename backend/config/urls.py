from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """API liveness only; does not check database readiness."""
    return Response({"status": "ok", "service": "Sheet2Service"})


urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/", include("uploads.urls")),
]
