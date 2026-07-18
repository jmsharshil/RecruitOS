from audit.models import AuditLog

def log_action(user, action, entity, entity_id, details, organization=None):
    """Log an action to the audit trail. organization can be explicitly provided for system/public actions (user=None)."""
    if organization is None and user is not None:
        organization = getattr(user, 'organization', None)
    user_name = getattr(user, 'name', 'System') if user is not None else 'System'

    AuditLog.objects.create(
        user=user,
        organization=organization,
        user_name=user_name,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        details=details
    )
