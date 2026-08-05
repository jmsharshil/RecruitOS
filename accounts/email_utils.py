"""
accounts/email_utils.py

Org-aware email sending utilities with robust fallback.

- Encrypts/decrypts SMTP passwords using Fernet symmetric encryption.
- Builds per-org Django email backend instances dynamically.
- Renders templates with org branding injected (logo, colors, footer).
- **Enforces fallback to global SMTP credentials** (from .env / settings.EMAIL_*) 
  when OrganizationEmailConfig is missing, inactive, or fails at send-time 
  (e.g. SMTPAuthenticationError). This fixes set_pin email delivery failures.
"""
import base64
import logging
import smtplib
from django.conf import settings
from accounts.models import OrganizationEmailConfig, User
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.template.loader import render_to_string
from django.template import Template, Context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Encryption helpers (Fernet / cryptography library)
# Falls back to base64 obfuscation if cryptography is not installed so the
# app still runs during development without the extra dependency.
# ---------------------------------------------------------------------------

def _get_fernet():
    """Return a Fernet instance keyed from settings.EMAIL_ENCRYPTION_KEY."""
    try:
        from cryptography.fernet import Fernet
        key = getattr(settings, 'EMAIL_ENCRYPTION_KEY', None)
        if not key:
            # Auto-generate and warn — prod should always set this
            logger.warning(
                "EMAIL_ENCRYPTION_KEY not set in settings. "
                "SMTP passwords will use base64 obfuscation only."
            )
            return None
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)
    except ImportError:
        logger.warning("cryptography package not installed; SMTP passwords use base64 obfuscation.")
        return None


def encrypt_value(raw: str) -> str:
    """Encrypt a plaintext string. Returns a string safe to store in DB."""
    if not raw:
        return ''
    fernet = _get_fernet()
    if fernet:
        return fernet.encrypt(raw.encode()).decode()
    # Fallback: base64 (not secure, only for dev)
    return base64.b64encode(raw.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a previously encrypted string. Returns plaintext."""
    if not encrypted:
        return ''
    fernet = _get_fernet()
    try:
        if fernet:
            return fernet.decrypt(encrypted.encode()).decode()
        # Fallback: base64
        return base64.b64decode(encrypted.encode()).decode()
    except Exception as exc:
        logger.error(f"Failed to decrypt SMTP password: {exc}")
        return ''


# ---------------------------------------------------------------------------
# Email backend factory
# ---------------------------------------------------------------------------

def get_org_email_connection(organization):
    """
    Return a Django email backend for the organization.
    If no active OrganizationEmailConfig (or missing/invalid credentials), falls back
    to the default backend configured in settings.py (.env EMAIL_* vars).
    Note: SMTP auth failures are caught at send-time in send_org_email() for
    explicit global retry (see there for full fallback logic).
    """
    if not organization:
        return get_connection()

    try:
        cfg = organization.email_config
        if not cfg.is_active or not cfg.smtp_username or not cfg.get_smtp_password():
            raise AttributeError("inactive or unconfigured")
        # Prefer org config but fallback to settings.py values for missing fields
        return SMTPBackend(
            host=cfg.smtp_host or getattr(settings, 'EMAIL_HOST', 'smtp.gmail.com'),
            port=cfg.smtp_port or getattr(settings, 'EMAIL_PORT', 587),
            username=cfg.smtp_username,
            password=cfg.get_smtp_password(),
            use_tls=cfg.use_tls,
            use_ssl=cfg.use_ssl,
            fail_silently=False,
        )
    except Exception as exc:
        # No valid org config — use Django default from settings.py
        logger.info(
            f"No active/valid email config for org '{getattr(organization, 'name', 'N/A')}': {exc}. "
            f"Using default from settings.py (EMAIL_HOST={getattr(settings, 'EMAIL_HOST', 'N/A')})"
        )
        return get_connection()


def get_org_from_email(organization):
    """Return the 'From' address to use for this org's emails."""
    try:
        cfg = organization.email_config
        if cfg.is_active and cfg.from_email:
            name = cfg.from_name or organization.name
            return f"{name} <{cfg.from_email}>"
    except Exception:
        pass
    return settings.DEFAULT_FROM_EMAIL


# ---------------------------------------------------------------------------
# Branding / template helpers
# ---------------------------------------------------------------------------

def get_org_branding(organization, template_key: str) -> dict:
    """
    Return a dict of branding variables for the given org + template key.
    Always returns a valid dict (defaults if no org template configured).
    """
    defaults = {
        'org_name': organization.name if organization else 'RecruitOS',
        'org_logo': '',
        'primary_color': '#1e40af',
        'secondary_color': '#f8fafc',
        'footer_text': f'© {organization.name} — Powered by RecruitOS' if organization else '© RecruitOS',
        'custom_html': '',
    }
    if not organization:
        return defaults
    try:
        tmpl = organization.email_templates.filter(
            template_key=template_key, is_active=True
        ).first()
        if tmpl:
            return {
                'org_name': organization.name,
                'org_logo': tmpl.logo_url,
                'primary_color': tmpl.primary_color,
                'secondary_color': tmpl.secondary_color,
                'footer_text': tmpl.footer_text or defaults['footer_text'],
                'custom_html': tmpl.custom_html,
            }
    except Exception:
        pass
    return defaults


# ---------------------------------------------------------------------------
# Main send helper
# ---------------------------------------------------------------------------

def send_org_email(organization, subject: str, template_name: str, context: dict, recipient_list: list, from_email_override: str = None, attachments: list = None):
    """
    Render an email template with org branding and send via the org's SMTP
    (or Django default if not configured). **Enforces fallback to global
    credentials from settings.py / .env on SMTP auth or connection failures.**
    This ensures set_pin emails (and others) always deliver when org config
    is broken (e.g. invalid Outlook/Gmail credentials).

    :param organization: Organization instance (may be None for system emails)
    :param subject: Email subject string
    :param template_name: Template key / file name (e.g. 'set_pin')
    :param context: Template context dict (branding vars are auto-injected)
    :param recipient_list: List of recipient email strings
    :param from_email_override: Optional email to use in the From header
    :param attachments: Optional list of tuples (filename, content, mimetype)
    """
    branding = get_org_branding(organization, template_name)
    context.update(branding)

    # Check for custom_html override first
    if branding.get('custom_html'):
        try:
            html_message = Template(branding['custom_html']).render(Context(context))
        except Exception as exc:
            logger.warning(f"Custom HTML render failed for {template_name}: {exc}")
            html_message = render_to_string(f'emails/{template_name}.html', context)
    else:
        html_message = render_to_string(f'emails/{template_name}.html', context)

    plain_message = context.get('plain_message', subject)
    
    if from_email_override:
        org_name = branding.get('org_name', getattr(organization, 'name', 'RecruitOS'))
        from_email = f"{org_name} <{from_email_override}>"
        
        # --- NEW: Check if the override user has Google API Tokens ---
        try:
            sender_user = User.objects.get(email=from_email_override)
            if sender_user.google_access_token:
                logger.info(f"Attempting to send email via Gmail API for {from_email_override}")
                # Create a MIME message
                message = MIMEMultipart('alternative')
                message['to'] = ", ".join(recipient_list)
                message['from'] = from_email
                message['subject'] = subject

                part1 = MIMEText(plain_message, 'plain')
                part2 = MIMEText(html_message, 'html')
                message.attach(part1)
                message.attach(part2)

                if attachments:
                    from email.mime.base import MIMEBase
                    from email import encoders
                    for filename, content, mimetype in attachments:
                        maintype, subtype = mimetype.split('/', 1)
                        part = MIMEBase(maintype, subtype)
                        part.set_payload(content)
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                        message.attach(part)

                raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

                creds = Credentials(
                    token=sender_user.google_access_token,
                    refresh_token=sender_user.google_refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None),
                    client_secret=getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None),
                )
                service = build('gmail', 'v1', credentials=creds)
                
                try:
                    sent_msg = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
                    logger.info(f"Successfully sent via Gmail API! Message ID: {sent_msg['id']}")
                    return  # Exit early, we sent it successfully via API
                except Exception as e:
                    logger.error(f"Gmail API send failed: {e}. Falling back to standard SMTP.")
        except User.DoesNotExist:
            pass
    else:
        from_email = get_org_from_email(organization)

    # Try org-specific connection first (may raise SMTP auth errors at send time)
    connection = get_org_email_connection(organization)

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=from_email,
            to=recipient_list,
            connection=connection,
        )
        msg.attach_alternative(html_message, 'text/html')
        
        if attachments:
            for filename, content, mimetype in attachments:
                msg.attach(filename, content, mimetype)
                
        msg.send()
        print(f"==========> [DEBUG] Org SMTP send SUCCESS to {recipient_list}")
        logger.info(
            f"Email '{template_name}' sent to {recipient_list} "
            f"via org={getattr(organization, 'name', 'default')}"
        )
        return
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPException, OSError) as exc:
        print(f"==========> [DEBUG] Org SMTP FAILED (Auth/Connection): {exc}")
        logger.warning(
            f"Org SMTP failed for '{template_name}' to {recipient_list} "
            f"(org={getattr(organization, 'name', 'N/A')}): {exc}. "
            "Falling back to global credentials from .env/settings."
        )
    except Exception as exc:
        logger.error(f"Unexpected error preparing email '{template_name}': {exc}")
        raise

    # === GLOBAL FALLBACK ===
    try:
        global_conn = get_connection(fail_silently=False)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=from_email,
            to=recipient_list,
            connection=global_conn,
        )
        msg.attach_alternative(html_message, 'text/html')
        
        if attachments:
            for filename, content, mimetype in attachments:
                msg.attach(filename, content, mimetype)
                
        msg.send()
        print(f"==========> [DEBUG] Global Fallback SMTP send SUCCESS to {recipient_list}")
        logger.info(
            f"Email '{template_name}' sent to {recipient_list} "
            f"via GLOBAL fallback credentials (settings.EMAIL_*)"
        )
    except Exception as fallback_exc:
        print(f"==========> [DEBUG] Global Fallback SMTP FAILED: {fallback_exc}")
        logger.error(
            f"Global fallback ALSO failed for '{template_name}' to {recipient_list}: {fallback_exc}"
        )
        raise
