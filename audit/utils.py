from audit.models import AuditLog
from django.utils import timezone

def log_action(user, action, entity, entity_id, details):
    AuditLog.objects.create(
        user=user,
        organization=user.organization if user else None,
        user_name=user.name if user else 'System',
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        details=details,
        timestamp=timezone.now()
    )
