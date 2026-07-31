import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, Organization, UserRole
from accounts.serializers import UserBriefSerializer
from audit.utils import log_action

logger = logging.getLogger(__name__)

class GoogleLoginView(APIView):
    """
    Endpoint: POST /api/v1/auth/google/
    Expects: { "id_token": "google_id_token_here" }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get("id_token")
        access_token = request.data.get("access_token")
        refresh_token = request.data.get("refresh_token")
        expires_in = request.data.get("expires_in")  # seconds

        auth_code = request.data.get("code")

        if auth_code:
            try:
                from google_auth_oauthlib.flow import Flow
                client_config = {
                    "web": {
                        "client_id": getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', ''),
                        "client_secret": getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', ''),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                }
                flow = Flow.from_client_config(
                    client_config,
                    scopes=['openid', 'email', 'profile', 'https://www.googleapis.com/auth/gmail.send'],
                    redirect_uri='postmessage'
                )
                
                # Google rewrites basic scopes to full URLs, which causes OAuthLib to throw an error
                # Relaxing token scope enforcement prevents this error.
                import os
                os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
                
                flow.fetch_token(code=auth_code)
                credentials = flow.credentials
                
                token = credentials.id_token
                access_token = credentials.token
                refresh_token = credentials.refresh_token
                
                if credentials.expiry:
                    import datetime
                    expires_in = (credentials.expiry - datetime.datetime.utcnow()).total_seconds()
            except Exception as e:
                logger.error(f"Google code exchange failed: {e}")
                return Response({"error": "Failed to exchange auth code"}, status=status.HTTP_400_BAD_REQUEST)

        if not token:
            return Response({"error": "id_token is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Verify the Google Token
        try:
            # We accept any Client ID for now
            idinfo = id_token.verify_oauth2_token(token, requests.Request())
            
            email = idinfo.get("email")
            name = idinfo.get("name")
            picture_url = idinfo.get("picture")
            
            if not email:
                return Response({"error": "Email not found in Google token"}, status=status.HTTP_400_BAD_REQUEST)
                
            email_clean = email.strip().lower()

            # 2. Check if user exists
            user = User.objects.filter(email__iexact=email_clean).first()

            if user:
                # User exists -> Log them in
                logger.info(f"Google Login successful for existing user: {email_clean}")
                log_action(user, 'logged_in', 'User', user.id, "Logged in via Google SSO", organization=getattr(user, 'organization', None))

                # If user doesn't have an avatar, try to download and save their Google picture
                if not user.avatar and picture_url:
                    try:
                        import requests as http_requests
                        from django.core.files.base import ContentFile
                        response = http_requests.get(picture_url, timeout=5)
                        if response.status_code == 200:
                            user.avatar.save(f"{user.id}_google_avatar.jpg", ContentFile(response.content), save=True)
                    except Exception as e:
                        logger.warning(f"Failed to fetch or save Google avatar for {email_clean}: {e}")

                # Save Google Tokens if provided
                if access_token:
                    user.google_access_token = access_token
                    if refresh_token:
                        user.google_refresh_token = refresh_token
                    if expires_in:
                        from django.utils import timezone
                        from datetime import timedelta
                        user.google_token_expiry = timezone.now() + timedelta(seconds=int(expires_in))
                    user.save(update_fields=['google_access_token', 'google_refresh_token', 'google_token_expiry'])
            else:
                # User does NOT exist -> Block login
                logger.warning(f"Google Login attempted by unregistered user: {email_clean}")
                return Response(
                    {"error": "This email is not registered in our system. Please contact your admin to create an account first."}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            # 3. Generate JWT Tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": UserBriefSerializer(user, context={"request": request}).data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            # Invalid token
            logger.error(f"Google Login failed (Invalid token): {e}")
            return Response({"error": "Invalid Google token"}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Google Login unexpected error: {e}")
            return Response({"error": "Internal server error during Google login"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class GoogleConfigView(APIView):
    """
    Endpoint: GET /api/v1/auth/google-config/
    Returns the Google Client ID configured in the backend
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
        if not client_id:
            return Response({"error": "Google Client ID not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({"client_id": client_id}, status=status.HTTP_200_OK)
