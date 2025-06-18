from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
import string
import random
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from cloudinary.models import CloudinaryField

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, max_length=255)
    quota = models.PositiveIntegerField(
        default=100, 
        help_text='Number of URLs a user can shorten per month'
    )
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

class ShortenedURL(models.Model):
    original_url = models.URLField(max_length=2048)
    short_code = models.CharField(max_length=10, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shortened_urls',
        null=True,
        blank=True
    )
    visit_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True, null=True)
    qr_code = CloudinaryField('qr_codes', blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['short_code']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.short_code} -> {self.original_url}"

    @staticmethod
    def generate_short_code(length=6):
        """Generate a random short code"""
        while True:
            code = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
            if not ShortenedURL.objects.filter(short_code=code).exists():
                return code

    def save(self, *args, **kwargs):
        if not self.short_code:
            self.short_code = self.generate_short_code()
        super().save(*args, **kwargs)
    def generate_qr_code(self):
        import cloudinary.uploader
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # Use settings.DOMAIN if available, otherwise use a default
        domain = getattr(settings, 'DOMAIN', 'localhost:8000')
        short_url = f"http://{domain}/{self.short_code}"
        qr.add_data(short_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        try:
            # Upload directly to Cloudinary
            upload_result = cloudinary.uploader.upload(
                buffer.getvalue(),
                public_id=f"qr_codes/qr_{self.short_code}",
                format="png",
                resource_type="image"
            )
            
            # Store the Cloudinary public_id in the CloudinaryField
            from cloudinary import CloudinaryImage
            self.qr_code = CloudinaryImage(upload_result['public_id'])
            
            # Save the model instance
            self.save(update_fields=['qr_code'])
            
        except Exception as e:
            print(f"Error uploading QR code to Cloudinary: {e}")
            # Handle the error as needed
            
        finally:
            buffer.close()





