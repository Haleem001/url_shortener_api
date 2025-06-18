from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from shortener.auth import RegisterView, CustomTokenObtainPairView
from shortener.views import ShortenURLView, RedirectView, URLAnalyticsView
from django.urls import path
from . import views

urlpatterns = [
       
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    path('shorten/', views.ShortenURLView.as_view(), name='shorten-url'),
    
    path('urls/', views.URLListView.as_view(), name='url-list'),
    
   
    path('urls/<str:short_code>/', views.URLDetailView.as_view(), name='url-detail'),
    path('urls/<str:short_code>/edit/', views.URLUpdateView.as_view(), name='url-update'),
    path('urls/<str:short_code>/delete/', views.URLDeleteView.as_view(), name='url-delete'),
    
    
    path('urls/<str:short_code>/toggle/', views.URLToggleActiveView.as_view(), name='url-toggle'),

    path('urls/bulk/delete/', views.URLBulkDeleteView.as_view(), name='url-bulk-delete'),
    path('urls/bulk/toggle/', views.URLBulkToggleView.as_view(), name='url-bulk-toggle'),
    
  
    path('stats/<str:short_code>/', views.url_stats, name='url-stats'),
    path('analytics/<str:short_code>/', views.URLAnalyticsView.as_view(), name='url-analytics'),
   
    path('qr/<str:short_code>/', views.QRCodeView.as_view(), name='qr-code'),
    
  
    path('<str:short_code>/', views.RedirectView.as_view(), name='redirect'),
]
