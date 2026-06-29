from rest_framework.views import exception_handler
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    
    if response is not None:
        custom_response = {
            "error": "Validation failed" if response.status_code == 400 else "Error",
            "detail": response.data.get('detail', 'An error occurred.') if isinstance(response.data, dict) else str(response.data),
            "field_errors": {}
        }
        
        if response.status_code == 400 and isinstance(response.data, dict):
            for key, value in response.data.items():
                if key != 'detail':
                    custom_response["field_errors"][key] = value if isinstance(value, list) else [value]
                    
        response.data = custom_response
    
    return response
