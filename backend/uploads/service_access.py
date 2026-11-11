"""Which persona may use which feature of a generated reservation service."""
from rest_framework.exceptions import ValidationError

from .views import owned

BOOKING_FEATURES = ("make_reservation", "my_reservations", "review_reservations", "manage_schedule")


def service_upload(request, pk):
    upload = owned(request, pk)
    if not upload.service_config:
        raise ValidationError({"detail": "서비스가 아직 생성되지 않았습니다. 파일을 업로드해 생성해 주세요."})
    return upload


def has_feature(config, *features):
    return any(feature in persona["features"] for persona in config["personas"] for feature in features)


def persona_of(config, persona_id):
    return next((persona for persona in config["personas"] if persona["id"] == persona_id), None)


def requested_persona(request, config, *features):
    """The persona named in ?persona=, which must exist in this service and hold one of the features."""
    persona_id = request.query_params.get("persona") or (request.data.get("persona") if isinstance(request.data, dict) else None)
    persona = persona_of(config, persona_id) if persona_id else None
    if persona is None:
        raise ValidationError({"detail": "이 서비스에 없는 역할입니다."})
    if features and not any(feature in persona["features"] for feature in features):
        raise ValidationError({"detail": "이 역할에서는 사용할 수 없는 기능입니다."})
    return persona
