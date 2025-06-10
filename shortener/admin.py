from django.contrib import admin
from .models import ShortenedURL

@admin.register(ShortenedURL)
class ShortenedURLAdmin(admin.ModelAdmin):
    list_display = ('short_code', 'original_url', 'visit_count', 'created_at')
    search_fields = ('original_url', 'short_code')
    readonly_fields = ('visit_count', 'created_at')