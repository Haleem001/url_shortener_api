from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from shortener.auth import RegisterView, CustomTokenObtainPairView
from shortener.views import ShortenURLView, RedirectView, URLAnalyticsView

urlpatterns = [
    # Authentication
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # URL Shortener
    path('api/shorten/', ShortenURLView.as_view(), name='shorten-url'),
    path('api/analytics/<str:short_code>/', URLAnalyticsView.as_view(), name='url-analytics'),
    path('<str:short_code>/', RedirectView.as_view(), name='redirect'),
]