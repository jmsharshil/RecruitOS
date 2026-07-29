import uuid
from django.db import models
from common.models import BaseModel
from accounts.models import User

class ClientStatus(models.TextChoices):
    ACTIVE   = 'active'
    INACTIVE = 'inactive'
    ON_HOLD  = 'on-hold'

class Client(BaseModel):
    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id               = models.CharField(max_length=20, blank=True)  # auto-generated: CLI-0001 (unique per org)
    #Company Details
    company_name            = models.CharField(max_length=200)
    client_name             = models.CharField(max_length=150)
    email                   = models.EmailField()
    alternative_email       = models.EmailField(blank=True)
    contact                 = models.CharField(max_length=20)
    alternative_contact     = models.CharField(max_length=20, blank=True)
    website                 = models.URLField(blank=True)
    linkedin                = models.URLField(blank=True)
    #Location
    street                  = models.TextField(blank=True)
    city                    = models.CharField(max_length=100)
    state                   = models.CharField(max_length=100)
    country                 = models.CharField(max_length=100)
    postal_code             = models.CharField(max_length=20, blank=True)
    client_location         = models.CharField(max_length=100,blank=True)
    #Business Details
    industry                = models.CharField(max_length=100)
    gst_number              = models.CharField(max_length=50, blank=True)
    status                  = models.CharField(max_length=20, choices=ClientStatus.choices, default=ClientStatus.ACTIVE)
    #Commercials & Agreement
    agreement_date          = models.DateField(null=True, blank=True)
    payment_period_days     = models.PositiveIntegerField(null=True, blank=True)
    replacement_period_days = models.PositiveIntegerField(null=True, blank=True)
    commercial_decided      = models.TextField(blank=True)  # Now text (e.g. "15% margin, net-30") instead of boolean flag
    agreement_document      = models.FileField(
        upload_to='client_agreements/',
        null=True,
        blank=True
    )
    agreement_document_name = models.CharField(max_length=255, blank=True)
    created_by              = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_clients')
    #Internal Notes
    notes                   = models.TextField(blank=True)
    #Team Members (Custom roles like HR, Development, etc.)
    team_members            = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ('organization', 'client_id')

    def save(self, *args, **kwargs):
        if not self.client_id:
            # Organization-scoped client_id generation
            last = Client.objects.filter(organization=self.organization).order_by('-created_at').first()
            next_num = (int(last.client_id.split('-')[1]) + 1) if (last and '-' in last.client_id) else 1
            self.client_id = f"CLI-{next_num:04d}"
        super().save(*args, **kwargs)

class ClientDocument(BaseModel):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client      = models.ForeignKey(Client, related_name='documents', on_delete=models.CASCADE)
    file        = models.FileField(upload_to='client_docs/')
    file_name   = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class POCType(models.TextChoices):
    HIRING  = 'hiring'
    PAYMENT = 'payment'

class POC(BaseModel):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client      = models.ForeignKey(Client, related_name='pocs', on_delete=models.CASCADE)
    poc_type    = models.CharField(max_length=10, choices=POCType.choices)
    name        = models.CharField(max_length=150)
    email       = models.EmailField()
    designation = models.CharField(max_length=150)
    contact     = models.CharField(max_length=20)
    linkedin    = models.URLField(blank=True)
    description = models.TextField(blank=True)
