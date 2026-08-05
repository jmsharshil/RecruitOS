import json
from django.utils.deprecation import MiddlewareMixin
from audit.models import AuditLog, AuditActionType

class AuditLogMiddleware(MiddlewareMixin):
    def generate_event_name(self, method, path):
        # Remove /api/v1/ or /api/
        clean_path = path.replace('/api/v1/', '').replace('/api/', '')
        # Remove trailing slash
        clean_path = clean_path.strip('/')
        # Replace hyphens and slashes with spaces, handle UUIDs loosely
        parts = clean_path.split('/')
        # Filter out parts that look like UUIDs or IDs (rough check: length > 20 or digits)
        readable_parts = [p for p in parts if len(p) < 20 and not p.isdigit()]
        
        resource_name = " ".join(readable_parts).replace('-', ' ')
        if not resource_name:
            resource_name = "Resource"
            
        resource_name = resource_name.title()
        
        if method == 'GET':
            return f"Fetched {resource_name}"
        elif method == 'POST':
            if 'login' in path:
                return "User logged in"
            return f"Created {resource_name}"
        elif method in ['PUT', 'PATCH']:
            return f"Updated {resource_name}"
        elif method == 'DELETE':
            return f"Deleted {resource_name}"
        return f"Accessed {resource_name}"

    def process_request(self, request):
        if not request.path.startswith('/api/'):
            return
            
        # Skip logging for the audit API itself
        if request.path.startswith('/api/v1/audit/'):
            return
            
        request._audit_body = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                body = request.body
                if body:
                    data = json.loads(body)
                    # Redact sensitive fields
                    if 'password' in data:
                        data['password'] = '***REDACTED***'
                    if 'old_password' in data:
                        data['old_password'] = '***REDACTED***'
                    if 'new_password' in data:
                        data['new_password'] = '***REDACTED***'
                    request._audit_body = data
            except Exception:
                pass

    def process_response(self, request, response):
        # We only log requests to /api/
        if not request.path.startswith('/api/'):
            return response

        # Skip logging for the audit API itself
        if request.path.startswith('/api/v1/audit/'):
            return response

        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            # For login, we won't have request.user since simplejwt sets it later or it's a separate API.
            # We'll rely on the Login endpoint itself to log the login, or we just skip if no user.
            return response

        # Map HTTP methods to actions
        method = request.method
        event = self.generate_event_name(method, request.path)
        
        if method == 'GET':
            action = AuditActionType.READ
        elif method == 'POST':
            if 'login' in request.path:
                action = AuditActionType.LOGIN
            else:
                action = AuditActionType.CREATED
        elif method in ['PUT', 'PATCH']:
            action = AuditActionType.UPDATED
        elif method == 'DELETE':
            action = AuditActionType.DELETED
        else:
            action = AuditActionType.READ

        # Determine organization and user info
        organization = getattr(user, 'organization', None)
        user_name = getattr(user, 'name', 'System')
        user_role = getattr(user, 'role', '')

        # IP Address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        if ip_address:
            if ip_address.startswith('['):
                ip_address = ip_address.split(']')[0][1:]
            elif ip_address.count(':') == 1:
                ip_address = ip_address.split(':')[0]

        # User Agent
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Request Body
        request_body = getattr(request, '_audit_body', None)
        
        # Response Summary
        response_summary = None
        if response.get('Content-Type') == 'application/json':
            try:
                resp_data = json.loads(response.content)
                # Store the actual data. If it's a very long array, we can truncate it.
                if isinstance(resp_data, list) and len(resp_data) > 20:
                    response_summary = resp_data[:20] + [{"msg": f"...and {len(resp_data) - 20} more items"}]
                else:
                    response_summary = resp_data
            except Exception:
                pass

        # Create the audit log
        AuditLog.objects.create(
            user=user,
            organization=organization,
            user_name=user_name,
            user_role=user_role,
            user_email=getattr(user, 'email', None) if user else None,
            action=action,
            event=event,
            method=method,
            status_code=response.status_code,
            path=request.path,
            ip_address=ip_address,
            user_agent=user_agent,
            request_body=request_body,
            response_summary=response_summary
        )

        return response
