import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, Organization, UserRole
from accounts.serializers import UserBriefSerializer
from audit.utils import log_action

logger = logging.getLogger(__name__)


class MicrosoftLoginView(APIView):
    """
    Endpoint: POST /api/v1/auth/microsoft/
    Expects EITHER:
      { "id_token": "microsoft_id_token_here" }
    OR (auth-code flow, e.g. from MSAL.js / mobile MSAL SDK):
      { "code": "auth_code_here" }
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
                import msal

                tenant = getattr(settings, 'MICROSOFT_OAUTH_TENANT_ID', 'common')
                authority = f"https://login.microsoftonline.com/{tenant}"

                msal_app = msal.ConfidentialClientApplication(
                    client_id=getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', ''),
                    client_credential=getattr(settings, 'MICROSOFT_OAUTH_CLIENT_SECRET', ''),
                    authority=authority,
                )

                result = msal_app.acquire_token_by_authorization_code(
                    code=auth_code,
                    scopes=['User.Read', 'Mail.Send', 'MailboxSettings.Read'],
                    redirect_uri=getattr(settings, 'MICROSOFT_OAUTH_REDIRECT_URI', 'postmessage'),
                )

                if 'error' in result:
                    logger.error(f"Microsoft code exchange failed: {result.get('error_description')}")
                    return Response({"error": "Failed to exchange auth code"}, status=status.HTTP_400_BAD_REQUEST)

                token = result.get('id_token')
                access_token = result.get('access_token')
                refresh_token = result.get('refresh_token')
                expires_in = result.get('expires_in')

            except Exception as e:
                logger.error(f"Microsoft code exchange failed: {e}")
                return Response({"error": "Failed to exchange auth code"}, status=status.HTTP_400_BAD_REQUEST)

        if not token:
            return Response({"error": "id_token is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Verify the Microsoft Token
        try:
            idinfo = self._verify_microsoft_token(token)

            email = idinfo.get("email") or idinfo.get("preferred_username") or idinfo.get("upn")
            name = idinfo.get("name")

            if not email:
                return Response({"error": "Email not found in Microsoft token"}, status=status.HTTP_400_BAD_REQUEST)

            email_clean = email.strip().lower()

            # 2. Check if user exists
            user = User.objects.filter(email__iexact=email_clean).first()

            if user:
                # User exists -> Log them in
                logger.info(f"Microsoft Login successful for existing user: {email_clean}")
                log_action(user, 'logged_in', 'User', user.id, "Logged in via Microsoft SSO", organization=getattr(user, 'organization', None))

                # If user doesn't have an avatar, try to fetch their Microsoft Graph profile photo
                if not user.avatar and access_token:
                    try:
                        import requests as http_requests
                        from django.core.files.base import ContentFile
                        photo_response = http_requests.get(
                            "https://graph.microsoft.com/v1.0/me/photo/$value",
                            headers={"Authorization": f"Bearer {access_token}"},
                            timeout=5,
                        )
                        if photo_response.status_code == 200:
                            user.avatar.save(f"{user.id}_microsoft_avatar.jpg", ContentFile(photo_response.content), save=True)
                    except Exception as e:
                        logger.warning(f"Failed to fetch or save Microsoft avatar for {email_clean}: {e}")

                # Save Microsoft Tokens if provided
                if access_token:
                    user.microsoft_access_token = access_token
                    if refresh_token:
                        user.microsoft_refresh_token = refresh_token
                    if expires_in:
                        from django.utils import timezone
                        from datetime import timedelta
                        user.microsoft_token_expiry = timezone.now() + timedelta(seconds=int(expires_in))
                    user.save(update_fields=['microsoft_access_token', 'microsoft_refresh_token', 'microsoft_token_expiry'])
            else:
                # User does NOT exist -> Block login
                logger.warning(f"Microsoft Login attempted by unregistered user: {email_clean}")
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
            logger.error(f"Microsoft Login failed (Invalid token): {e}")
            return Response({"error": "Invalid Microsoft token"}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Microsoft Login unexpected error: {e}")
            return Response({"error": "Internal server error during Microsoft login"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _verify_microsoft_token(self, token):
        """
        Verifies a Microsoft (Azure AD / Entra ID) id_token using Microsoft's
        published JWKS, mirroring what google.oauth2.id_token.verify_oauth2_token
        does for Google above. Raises ValueError on any validation failure.
        """
        import jwt
        from jwt import PyJWKClient

        tenant = getattr(settings, 'MICROSOFT_OAUTH_TENANT_ID', 'common')
        client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', '')

        jwks_url = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"

        try:
            jwk_client = PyJWKClient(jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token)

            idinfo = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=client_id,
                options={"verify_exp": True},
            )
            return idinfo
        except jwt.PyJWTError as e:
            raise ValueError(f"Token verification failed: {e}")


class MicrosoftConfigView(APIView):
    """
    Endpoint: GET /api/v1/auth/microsoft-config/
    Returns the Microsoft Client ID (and tenant) configured in the backend
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', None)
        tenant_id = getattr(settings, 'MICROSOFT_OAUTH_TENANT_ID', 'common')

        if not client_id:
            return Response({"error": "Microsoft Client ID not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"client_id": client_id, "tenant_id": tenant_id}, status=status.HTTP_200_OK)