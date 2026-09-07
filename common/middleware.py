import re

class NormalizeUrlMiddleware:
    """
    Middleware to normalize URLs by replacing double slashes (//) with a single slash (/).
    This handles cases where a frontend client accidentally sends requests with double slashes
    (e.g., //api/v1/auth/google-config/).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '//' in request.path_info:
            request.path_info = re.sub(r'/+', '/', request.path_info)
        return self.get_response(request)

