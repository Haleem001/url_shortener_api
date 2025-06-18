from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from io import BytesIO
from django.core.files.base import ContentFile
import qrcode

from .models import ShortenedURL
from .serializers import ShortenedURLSerializer

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
    """Create a new shortened URL"""
    queryset = ShortenedURL.objects.all()
    serializer_class = ShortenedURLSerializer
    throttle_classes = [AnonymousURLThrottle]
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """Handle URL shortening request with optional custom code and QR code generation."""
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

        # Check if URL already exists for this user (only if no custom code is provided)
        if not custom_code and request.user.is_authenticated:
            existing = ShortenedURL.objects.filter(
                original_url=original_url, 
                user=request.user
            ).first()
            
            if existing:
                # Generate QR code if it doesn't exist using model method
                if not existing.qr_code:
                    existing.generate_qr_code()
                
                serializer = self.get_serializer(existing)
                return Response(serializer.data, status=status.HTTP_200_OK)
        
        # Create new shortened URL
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Increment counter for anonymous users
        if not request.user.is_authenticated:
            self.increment_anonymous_counter(request)
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    def check_anonymous_limit(self, request):
        """Check if anonymous user has exceeded the 10 URL limit"""
        ip_address = self.get_client_ip(request)
        cache_key = f"anon_url_count_{ip_address}"
        current_count = cache.get(cache_key, 0)
        return current_count < 10

    def increment_anonymous_counter(self, request):
        """Increment the counter for anonymous user URL creation"""
        ip_address = self.get_client_ip(request)
        cache_key = f"anon_url_count_{ip_address}"
        current_count = cache.get(cache_key, 0)
        cache.set(cache_key, current_count + 1, 86400)

    def get_client_ip(self, request):
        """Get the client's IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def perform_create(self, serializer):
        instance = serializer.save()
        # Use the model's generate_qr_code method
        instance.generate_qr_code()

class URLListView(generics.ListAPIView):
    """List all URLs for authenticated users, with search and filtering"""
    serializer_class = ShortenedURLSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ShortenedURL.objects.filter(user=self.request.user).order_by('-created_at')
        
        # Search functionality
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(original_url__icontains=search) | 
                Q(short_code__icontains=search)
            )
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset

class URLDetailView(generics.RetrieveAPIView):
    """Retrieve a specific URL by ID or short_code"""
    serializer_class = ShortenedURLSerializer
    permission_classes = [AllowAny]
    lookup_field = 'short_code'

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return ShortenedURL.objects.filter(user=self.request.user)
        return ShortenedURL.objects.all()

class URLUpdateView(generics.UpdateAPIView):
    """Update a URL (only for authenticated users who own the URL)"""
    serializer_class = ShortenedURLSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'short_code'

    def get_queryset(self):
        return ShortenedURL.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

class URLDeleteView(generics.DestroyAPIView):
    """Delete a URL (only for authenticated users who own the URL)"""
    serializer_class = ShortenedURLSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'short_code'

    def get_queryset(self):
        return ShortenedURL.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {'message': 'URL deleted successfully'}, 
            status=status.HTTP_204_NO_CONTENT
        )

class URLToggleActiveView(generics.UpdateAPIView):
    """Toggle active status of a URL"""
    serializer_class = ShortenedURLSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'short_code'

    def get_queryset(self):
        return ShortenedURL.objects.filter(user=self.request.user)

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = not instance.is_active
        instance.save()
        
        serializer = self.get_serializer(instance)
        return Response({
            'message': f'URL {"activated" if instance.is_active else "deactivated"} successfully',
            'data': serializer.data
        })

# Keep your existing views
@api_view(['GET'])
@permission_classes([AllowAny])
def url_stats(request, short_code):
    url_obj = get_object_or_404(ShortenedURL, short_code=short_code)
    serializer = ShortenedURLSerializer(url_obj, context={'request': request})
    return Response(serializer.data)

class RedirectView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    
    def get(self, request, short_code):
        shortened_url = get_object_or_404(ShortenedURL, short_code=short_code)
        
        # Check if URL is active
        if not shortened_url.is_active:
            return HttpResponse(
                "<h1>URL Not Available</h1><p>This shortened URL has been deactivated.</p>",
                status=410
            )
        
        # Check if URL is flagged as malicious
        if shortened_url.is_flagged:
            warning_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Warning - Potentially Malicious URL</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #fff3cd; }}
                    .warning-container {{ max-width: 600px; margin: 0 auto; padding: 20px; 
                                        border: 2px solid #ffc107; border-radius: 8px; 
                                        background-color: #fff; }}
                    .warning-icon {{ font-size: 48px; color: #dc3545; text-align: center; }}
                    .warning-title {{ color: #dc3545; text-align: center; margin: 20px 0; }}
                    .warning-text {{ margin: 20px 0; line-height: 1.6; }}
                    .url-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 4px; 
                               word-break: break-all; margin: 20px 0; }}
                    .buttons {{ text-align: center; margin: 30px 0; }}
                    .btn {{ padding: 10px 20px; margin: 0 10px; text-decoration: none; 
                           border-radius: 4px; font-weight: bold; }}
                    .btn-danger {{ background-color: #dc3545; color: white; }}
                    .btn-secondary {{ background-color: #6c757d; color: white; }}
                    .btn:hover {{ opacity: 0.8; }}
                </style>
            </head>
            <body>
                <div class="warning-container">
                    <div class="warning-icon">⚠️</div>
                    <h1 class="warning-title">Warning: Potentially Malicious URL</h1>
                    <div class="warning-text">
                        <p>This shortened URL has been flagged as potentially malicious and may contain:</p>
                        <ul>
                            <li>Malware or viruses</li>
                            <li>Phishing attempts</li>
                            <li>Suspicious content</li>
                        </ul>
                        <p><strong>Reason:</strong> {shortened_url.flag_reason}</p>
                    </div>
                    <div class="url-info">
                        <strong>Destination URL:</strong><br>
                        {shortened_url.original_url}
                    </div>
                    <div class="buttons">
                        <a href="javascript:history.back()" class="btn btn-secondary">Go Back</a>
                        <a href="{shortened_url.original_url}" class="btn btn-danger" 
                           onclick="return confirm('Are you sure you want to proceed to this potentially dangerous URL?')">
                           Proceed Anyway (Not Recommended)
                        </a>
                    </div>
                    <p style="text-align: center; color: #6c757d; font-size: 12px; margin-top: 30px;">
                        If you believe this URL has been incorrectly flagged, please contact support.
                    </p>
                </div>
            </body>
            </html>
            """
            return HttpResponse(warning_html)
        
        # If not flagged, proceed with normal redirect
        shortened_url.visit_count += 1
        shortened_url.save()
        return redirect(shortened_url.original_url)

class URLAnalyticsView(generics.RetrieveAPIView):
    queryset = ShortenedURL.objects.all()
    serializer_class = ShortenedURLSerializer
    lookup_field = 'short_code'
    permission_classes = [AllowAny]

class QRCodeView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    
    def get(self, request, short_code):
        shortened_url = get_object_or_404(ShortenedURL, short_code=short_code)
        
        if not shortened_url.qr_code:
            shortened_url.generate_qr_code()
            shortened_url.save()
        
        return redirect(shortened_url.qr_code.url)

# Bulk operations for authenticated users
class URLBulkDeleteView(generics.GenericAPIView):
    """Bulk delete URLs"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        url_ids = request.data.get('url_ids', [])
        if not url_ids:
            return Response(
                {'error': 'url_ids list is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        deleted_count = ShortenedURL.objects.filter(
            id__in=url_ids, 
            user=request.user
        ).delete()[0]

        return Response({
            'message': f'{deleted_count} URLs deleted successfully',
            'deleted_count': deleted_count
        })

class URLBulkToggleView(generics.GenericAPIView):
    """Bulk toggle active status of URLs"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        url_ids = request.data.get('url_ids', [])
        is_active = request.data.get('is_active', True)
        
        if not url_ids:
            return Response(
                {'error': 'url_ids list is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_count = ShortenedURL.objects.filter(
            id__in=url_ids, 
            user=request.user
        ).update(is_active=is_active)

        return Response({
            'message': f'{updated_count} URLs {"activated" if is_active else "deactivated"} successfully',
            'updated_count': updated_count
        })

class FrontendRedirectView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    
    def get(self, request, short_code):
        shortened_url = get_object_or_404(ShortenedURL, short_code=short_code)
        
        # Check if URL is active
        if not shortened_url.is_active:
            frontend_domain = 'localhost:5173'
            return redirect(f"http://{frontend_domain}/error?message=URL+not+available")
        
        # Check if URL is flagged as malicious
        if shortened_url.is_flagged:
            frontend_domain = getattr(settings, 'FRONTEND_DOMAIN', 'localhost:3000')
            return redirect(f"http://{frontend_domain}/warning?url={shortened_url.original_url}&reason={shortened_url.flag_reason}")
        
        # If not flagged, proceed with normal redirect
        shortened_url.visit_count += 1
        shortened_url.save()
        return redirect(shortened_url.original_url)
