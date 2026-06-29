import os
from django.core.exceptions import ValidationError

def validate_file_extension(value, allowed_extensions):
    ext = os.path.splitext(value.name)[1].lower()
    if not ext in allowed_extensions:
        raise ValidationError(f'Unsupported file extension. Allowed extensions are: {", ".join(allowed_extensions)}')

def validate_file_size(value, max_mb):
    if value.size > max_mb * 1024 * 1024:
        raise ValidationError(f'File size cannot exceed {max_mb} MB.')

def validate_resume(value):
    validate_file_extension(value, ['.pdf', '.doc', '.docx'])
    validate_file_size(value, 5)

def validate_client_doc(value):
    validate_file_extension(value, ['.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg'])
    validate_file_size(value, 10)

def validate_avatar(value):
    validate_file_extension(value, ['.png', '.jpg', '.jpeg', '.webp'])
    validate_file_size(value, 2)
