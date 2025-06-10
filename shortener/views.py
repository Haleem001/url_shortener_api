from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404, redirect
from .models import ShortenedURL
from .serializers import ShortenedURLSerializer
from django.conf import settings
from io import BytesIO
from django.core.files.base import ContentFile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.throttling import AnonRateThrottle
from rest_framework.permissions import AllowAny
from django.core.cache import cache
import qrcode

class AnonymousURLThrottle(AnonRateThrottle):
    """
    Custom throttle for anonymous URL shortening - 10 requests per day
    """
    scope = 'anon_url_shortening'
    
    def get_cache_key(self, request, view):
        """
        Get cache key based on IP address for anonymous users
        """
        if request.user.is_authenticated:
            return None  # No throttling for authenticated users
        
        # Use IP address as identifier for anonymous users
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

class ShortenURLView(generics.CreateAPIView):
    queryset = ShortenedURL.objects.all()
    serializer_class = ShortenedURLSerializer
    throttle_classes = [AnonymousURLThrottle]
    permission_classes = [AllowAny]  # Allow anonymous users

    def create(self, request, *args, **kwargs):
        """
        Handle URL shortening request with optional custom code and QR code generation.
        """
        # Check if user is anonymous and has exceeded limit
        if not request.user.is_authenticated:
            if not self.check_anonymous_limit(request):
                return Response(
                    {'error': 'Anonymous users can only shorten 10 URLs per day. Please register for unlimited access.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
        
        original_url = request.data.get('original_url')
        custom_code = request.data.get('custom_code', '').strip()
        
        if not original_url:
            return Response(
                {'error': 'original_url is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if URL already exists (only if no custom code is provided)
        if not custom_code:
            existing = ShortenedURL.objects.filter(original_url=original_url).first()
            
            if existing:
                # Generate QR code if it doesn't exist
                if not existing.qr_code:
                    self._generate_qr_code(existing, request)
                    existing.save()
                
                # Build complete response with short URL
                domain = getattr(settings, 'DOMAIN', None) or request.get_host()
                short_url = f"{request.scheme}://{domain}/{existing.short_code}"
                
                serializer = self.get_serializer(existing)
                response_data = serializer.data
                response_data['short_url'] = short_url
                
                return Response(response_data, status=status.HTTP_200_OK)
        
        # Create new shortened URL
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Use custom code if provided, otherwise generate random one
        if custom_code:
            serializer.validated_data['short_code'] = custom_code
        
        self.perform_create(serializer)
        
        # Increment counter for anonymous users
        if not request.user.is_authenticated:
            self.increment_anonymous_counter(request)
        
        # Build complete response with short URL
        instance = serializer.instance
        domain = getattr(settings, 'DOMAIN', None) or request.get_host()
        short_url = f"{request.scheme}://{domain}/{instance.short_code}"
        
        response_data = serializer.data
        response_data['short_url'] = short_url
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    def check_anonymous_limit(self, request):
        """
        Check if anonymous user has exceeded the 10 URL limit
        """
        ip_address = self.get_client_ip(request)
        cache_key = f"anon_url_count_{ip_address}"
        current_count = cache.get(cache_key, 0)
        return current_count < 10

    def increment_anonymous_counter(self, request):
        """
        Increment the counter for anonymous user URL creation
        """
        ip_address = self.get_client_ip(request)
        cache_key = f"anon_url_count_{ip_address}"
        current_count = cache.get(cache_key, 0)
        # Set cache to expire after 24 hours (86400 seconds)
        cache.set(cache_key, current_count + 1, 86400)

    def get_client_ip(self, request):
        """
        Get the client's IP address
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def perform_create(self, serializer):
        """
        Save the instance and generate QR code after creation
        """
        instance = serializer.save()
        self._generate_qr_code(instance, self.request)

    def _generate_qr_code(self, instance, request):
        """
        Helper method to generate QR code
        """
        # Get the domain from the request if not in settings
        domain = getattr(settings, 'DOMAIN', None) or request.get_host()
        short_url = f"{request.scheme}://{domain}/{instance.short_code}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(short_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to model
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        filename = f"qr_{instance.short_code}.png"
        instance.qr_code.save(filename, ContentFile(buffer.getvalue()), save=False)
        buffer.close()

@api_view(['GET'])
@permission_classes([AllowAny])
def url_stats(request, short_code):
    url_obj = get_object_or_404(ShortenedURL, short_code=short_code)
    serializer = ShortenedURLSerializer(url_obj, context={'request': request})
    return Response(serializer.data)

class RedirectView(generics.GenericAPIView):
    permission_classes = [AllowAny]  # Allow anonymous users
    
    def get(self, request, short_code):
        shortened_url = get_object_or_404(ShortenedURL, short_code=short_code)
        shortened_url.visit_count += 1
        shortened_url.save()
        return redirect(shortened_url.original_url)

class URLAnalyticsView(generics.RetrieveAPIView):
    queryset = ShortenedURL.objects.all()
    serializer_class = ShortenedURLSerializer
    lookup_field = 'short_code'
    permission_classes = [AllowAny]  # Allow anonymous users

class QRCodeView(generics.GenericAPIView):
    permission_classes = [AllowAny]  # Allow anonymous users
    
    def get(self, request, short_code):
        shortened_url = get_object_or_404(ShortenedURL, short_code=short_code)
        
        if not shortened_url.qr_code:
            shortened_url.generate_qr_code()
            shortened_url.save()
        
        return redirect(shortened_url.qr_code.url)
