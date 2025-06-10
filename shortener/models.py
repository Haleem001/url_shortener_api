from django.db import models
import hashlib
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from io import BytesIO
from django.core.files.base import ContentFile
import qrcode
from django.conf import settings
from django.contrib.auth.models import AbstractUser
import random
import string

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, max_length=255)
    quota = models.PositiveIntegerField(default=100, help_text="Number of URLs a user can shorten per month")
        
    def __str__(self):
        return self.email

class ShortenedURL(models.Model):
    original_url = models.URLField(max_length=2000)
    short_code = models.CharField(max_length=10, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    visit_count = models.PositiveIntegerField(default=0)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True,  # Allow null for anonymous users
        blank=True  # Allow blank in forms
    )

    def generate_qr_code(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # Get the full short URL
        short_url = f"http://{settings.DOMAIN}/{self.short_code}"
        qr.add_data(short_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to model
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        filename = f"qr_{self.short_code}.png"
        
        # Ensure we're using Cloudinary storage
        buffer.seek(0)  # Reset buffer position
        self.qr_code.save(filename, ContentFile(buffer.getvalue()), save=True)
        buffer.close()


    def save(self, *args, **kwargs):
        if not self.short_code:
            # Generate short code if not provided
            self.short_code = self.generate_short_code()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_short_code(length=6):
        """Generate a random short code"""
        while True:
            code = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
            if not ShortenedURL.objects.filter(short_code=code).exists():
                return code

    def clean(self):
        # Validate URL format
        validator = URLValidator()
        try:
            validator(self.original_url)
        except ValidationError as e:
            raise ValidationError({'original_url': 'Enter a valid URL'})

    def __str__(self):
        return f"{self.short_code} -> {self.original_url}"
