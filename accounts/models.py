import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserRole(models.TextChoices):
    ADMIN     = 'admin'
    MANAGER   = 'manager'
    RECRUITER = 'recruiter'


class CustomUserManager(BaseUserManager):
    def create_user(self, email, name, role, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, role=role, **extra_fields)
        # Do not create password on normal user creation (unusable until set via Set PIN API)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, role, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if not password:
            raise ValueError('Superuser must have a password.')
        return self.create_user(email, name, role, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=150)
    email       = models.EmailField(unique=True)
    role        = models.CharField(max_length=20, choices=UserRole.choices)
    phone       = models.CharField(max_length=20, blank=True)
    avatar      = models.ImageField(upload_to='avatars/', null=True, blank=True)
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    created_by  = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='created_users')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users', null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['name', 'role']

    def __str__(self):
        return f"{self.name} ({self.email})"


class OrganizationEmailConfig(models.Model):
    """
    Per-organization SMTP email configuration.
    Allows each tenant to send emails from their own email account.
    Falls back to Django settings defaults when not configured.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='email_config'
    )
    smtp_host               = models.CharField(max_length=200, default='smtp.gmail.com')
    smtp_port               = models.PositiveIntegerField(default=587)
    smtp_username           = models.CharField(max_length=200, blank=True)
    # Password stored as Fernet-encrypted string; use set_smtp_password() / get_smtp_password()
    smtp_password_encrypted = models.TextField(blank=True)
    from_email              = models.EmailField(blank=True)
    from_name               = models.CharField(max_length=150, blank=True)
    use_tls                 = models.BooleanField(default=True)
    use_ssl                 = models.BooleanField(default=False)
    is_active               = models.BooleanField(default=True)
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    def set_smtp_password(self, raw_password: str):
        """Encrypt and store the SMTP password."""
        from accounts.email_utils import encrypt_value
        self.smtp_password_encrypted = encrypt_value(raw_password)

    def get_smtp_password(self) -> str:
        """Decrypt and return the SMTP password."""
        if not self.smtp_password_encrypted:
            return ''
        from accounts.email_utils import decrypt_value
        return decrypt_value(self.smtp_password_encrypted)

    def __str__(self):
        return f"Email config for {self.organization.name}"

    class Meta:
        verbose_name = 'Organization Email Config'
        verbose_name_plural = 'Organization Email Configs'


class EmailTemplate(models.Model):
    """
    Per-organization email template branding & optional custom HTML.
    template_key examples: 'set_pin', 'interview_reminder', 'client_submission'
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='email_templates'
    )
    template_key    = models.CharField(max_length=100)   # e.g. 'set_pin'
    logo_url        = models.URLField(blank=True)
    primary_color   = models.CharField(max_length=20, default='#1e40af')
    secondary_color = models.CharField(max_length=20, default='#f8fafc')
    footer_text     = models.TextField(blank=True)
    # Optional full HTML override — if set, replaces the default template file
    custom_html     = models.TextField(blank=True)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'template_key')
        verbose_name = 'Email Template'
        verbose_name_plural = 'Email Templates'

    def __str__(self):
        return f"{self.template_key} template for {self.organization.name}"
