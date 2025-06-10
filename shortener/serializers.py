from rest_framework import serializers
from .models import ShortenedURL
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.conf import settings
import re
class ShortenedURLSerializer(serializers.ModelSerializer):
    short_url = serializers.SerializerMethodField()
    qr_code_url = serializers.SerializerMethodField()
    custom_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = ShortenedURL
        fields = ['original_url', 'short_code', 'short_url', 'custom_code', 'visit_count', 'created_at', 'qr_code_url']
        read_only_fields = ['short_code', 'visit_count', 'created_at', 'qr_code_url']


        
    def validate_custom_code(self, value):
        """Validate custom short code"""
        if value:
            # Check if it contains only alphanumeric characters and hyphens/underscores
            if not re.match(r'^[a-zA-Z0-9_-]+$', value):
                raise serializers.ValidationError(
                    "Custom code can only contain letters, numbers, hyphens, and underscores."
                )
            
            # Check minimum length
            if len(value) < 3:
                raise serializers.ValidationError(
                    "Custom code must be at least 3 characters long."
                )
            
            # Check if custom code already exists
            if ShortenedURL.objects.filter(short_code=value).exists():
                raise serializers.ValidationError(
                    "This custom code is already taken. Please choose another one."
                )
        
        return value    
    
    def get_short_url(self, obj):
        request = self.context.get('request')
        if request:
            domain = getattr(settings,'DOMAIN', None) or request.get_host()
            return f"{request.scheme}://{domain}/{obj.short_code}"
        return f"{obj.short_code}"


    def get_qr_code_url(self, obj):
        if obj.qr_code:
            return self.context['request'].build_absolute_uri(obj.qr_code.url)
        return None
    





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


class ShortenedURLSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShortenedURL
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'short_code', 'visit_count', 'qr_code')
    
    def create(self, validated_data):
        # Handle user assignment
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['user'] = request.user
        else:
            validated_data['user'] = None  # Set to None for anonymous users
        
        return super().create(validated_data)