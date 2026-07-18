from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler that normalizes error responses to a consistent shape:
    {
      "error": "Human readable error type or message",
      "detail": "Specific error details",
      "field_errors": {"field": ["messages"]}  # only for 400 validation errors
    }
    Matches documented error shapes in docs/candidates.md and docs/jobs.md.
    Handles JWT auth header issues (e.g. malformed Bearer token) gracefully.
    """
    response = exception_handler(exc, context)
    
    if response is not None:
        data = response.data
        detail = data.get('detail') if isinstance(data, dict) else str(data)
        if not detail:
            detail = 'An error occurred.'

        # Determine top-level error type based on status or exception
        if isinstance(exc, (AuthenticationFailed, NotAuthenticated)) or response.status_code == 401:
            error_type = "Authentication failed"
            status_code = 401
        elif isinstance(exc, PermissionDenied) or response.status_code == 403:
            error_type = "Permission denied"
            status_code = 403
        elif response.status_code == 400:
            error_type = "Validation failed"
            status_code = 400
        elif response.status_code >= 500:
            error_type = "Server error"
        else:
            error_type = detail if isinstance(detail, str) and len(detail) < 100 else "Error"

        custom_response = {
            "error": error_type,
            "detail": detail,
            "field_errors": {}
        }
        
        # For validation errors, extract field-specific errors (matches docs for 400s)
        if response.status_code == 400 and isinstance(data, dict):
            for key, value in data.items():
                if key not in ('detail', 'error'):
                    custom_response["field_errors"][key] = (
                        value if isinstance(value, list) else [value]
                    )
            # If view returned {"error": "specific"}, promote it
            if 'error' in data and isinstance(data['error'], str):
                custom_response['error'] = data['error']
                custom_response['detail'] = data.get('detail', data['error'])
        
        # Override response data with our normalized shape (preserves original status_code)
        response.data = custom_response
    
    return response
