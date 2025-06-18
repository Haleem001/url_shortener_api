from rest_framework import serializers
from .models import ShortenedURL
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.conf import settings
from .url_validator import URLChecker
import re
from rest_framework import serializers
from .models import ShortenedURL, CustomUser
from .url_validator import URLChecker
import re

class ShortenedURLSerializer(serializers.ModelSerializer):
    short_url = serializers.SerializerMethodField()
    qr_code_url = serializers.SerializerMethodField()
    custom_code = serializers.CharField(max_length=10, required=False, write_only=True)
    frontend_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ShortenedURL
        fields = [
            'id', 'original_url', 'short_code', 'custom_code', 
            'short_url', 'frontend_url', 'qr_code_url', 'visit_count', 
            'created_at', 'is_active', 'is_flagged', 'flag_reason'
        ]
        read_only_fields = ['id', 'short_code', 'visit_count', 'created_at', 'short_url', 'frontend_url', 'qr_code_url']

    def get_short_url(self, obj):
        """Backend URL for API redirects"""
        request = self.context.get('request')
        if request:
            domain = getattr(settings, 'DOMAIN', None) or request.get_host()
            return f"{request.scheme}://{domain}/{obj.short_code}"
        return f"/{obj.short_code}"

    def get_frontend_url(self, obj):
        """Frontend URL for sharing"""
        frontend_domain = 'localhost:5173'
        return f"http://{frontend_domain}/{obj.short_code}"

    def get_qr_code_url(self, obj):
        if obj.qr_code:
            return obj.qr_code.url
        return None

    def validate_original_url(self, value):
        """Validate URL and check for malicious content"""
        # Check for malicious URLs
        is_malicious, reason = URLChecker.is_malicious(value)
        if is_malicious:
            raise serializers.ValidationError(f"URL appears to be malicious: {reason}")
        return value
        
    def validate_custom_code(self, value):
        """Validate custom short code"""
        if value:
            # Check if it contains only alphanumeric characters and hyphens/underscores
            if not re.match(r'^[a-zA-Z0-9_-]+$', value):  # Fixed the regex pattern
                raise serializers.ValidationError(
                    "Custom code can only contain letters, numbers, hyphens, and underscores."
                )
            
            # Check minimum length
            if len(value) < 3:
                raise serializers.ValidationError(
                    "Custom code must be at least 3 characters long."
                )
            
            # Check if custom code already exists (exclude current instance during update)
            queryset = ShortenedURL.objects.filter(short_code=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError(
                    "This custom code is already taken. Please choose another one."
                )
        
        return value

    def create(self, validated_data):
        # Handle custom code during creation
        custom_code = validated_data.pop('custom_code', None)
        if custom_code:
            validated_data['short_code'] = custom_code
        
        # Set user if authenticated
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['user'] = request.user
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Handle custom code during update
        custom_code = validated_data.pop('custom_code', None)
        if custom_code and custom_code != instance.short_code:
            validated_data['short_code'] = custom_code
            # Regenerate QR code with new short code
            instance.qr_code.delete(save=False)  # Delete old QR code
        
        # Update the instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # Generate new QR code if needed
        if not instance.qr_code or custom_code:
            instance.generate_qr_code()
            instance.save()
        
        return instance


User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        return token
