from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    User, ADRQuote, PriceAlert, Portfolio, Transaction, 
    MarketCorrelation, ExchangeRate, APIUsageLog
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model"""
    
    list_display = [
        'username', 'email', 'plan', 'daily_requests', 
        'last_request_reset', 'is_active', 'date_joined'
    ]
    list_filter = ['plan', 'is_active', 'is_staff', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['-date_joined']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Financial API Settings', {
            'fields': ('plan', 'api_key', 'daily_requests', 'last_request_reset')
        }),
    )
    
    readonly_fields = ['api_key', 'last_request_reset']
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return self.readonly_fields + ['date_joined']
        return self.readonly_fields


@admin.register(ADRQuote)
class ADRQuoteAdmin(admin.ModelAdmin):
    """Admin configuration for ADRQuote model"""
    
    list_display = [
        'ticker', 'price_usd_formatted', 'price_brl_formatted', 
        'exchange_rate', 'volume_formatted', 'change_percent_day', 
        'source', 'timestamp'
    ]
    list_filter = ['ticker', 'source', 'timestamp']
    search_fields = ['ticker']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    
    def price_usd_formatted(self, obj):
        return f"${obj.price_usd:.2f}"
    price_usd_formatted.short_description = 'Price USD'
    
    def price_brl_formatted(self, obj):
        return f"R${obj.price_brl:.2f}"
    price_brl_formatted.short_description = 'Price BRL'
    
    def volume_formatted(self, obj):
        return f"{obj.volume:,}"
    volume_formatted.short_description = 'Volume'


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    """Admin configuration for PriceAlert model"""
    
    list_display = [
        'user', 'ticker', 'condition_type', 'target_value', 
        'notification_channel', 'is_active', 'triggered_at', 'created_at'
    ]
    list_filter = [
        'condition_type', 'notification_channel', 'is_active', 
        'ticker', 'created_at'
    ]
    search_fields = ['user__username', 'ticker']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    """Admin configuration for Portfolio model"""
    
    list_display = [
        'user', 'ticker', 'quantity', 'average_price_usd', 
        'current_value_display', 'gain_loss_display', 'updated_at'
    ]
    list_filter = ['ticker', 'updated_at']
    search_fields = ['user__username', 'ticker']
    ordering = ['-updated_at']
    
    def current_value_display(self, obj):
        value_usd = obj.current_value_usd
        value_brl = obj.current_value_brl
        return f"${value_usd:.2f} (R${value_brl:.2f})"
    current_value_display.short_description = 'Current Value'
    
    def gain_loss_display(self, obj):
        gain_loss = obj.gain_loss_usd
        percentage = obj.gain_loss_percent
        color = 'green' if gain_loss >= 0 else 'red'
        return format_html(
            '<span style="color: {};">${:.2f} ({:.2f}%)</span>',
            color, gain_loss, percentage
        )
    gain_loss_display.short_description = 'Gain/Loss'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin configuration for Transaction model"""
    
    list_display = [
        'user', 'ticker', 'transaction_type', 'quantity', 
        'price_usd', 'total_value_display', 'date', 'created_at'
    ]
    list_filter = ['transaction_type', 'ticker', 'date']
    search_fields = ['user__username', 'ticker']
    ordering = ['-date', '-created_at']
    date_hierarchy = 'date'
    
    def total_value_display(self, obj):
        return f"${obj.total_value_usd:.2f} (R${obj.total_value_brl:.2f})"
    total_value_display.short_description = 'Total Value'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(MarketCorrelation)
class MarketCorrelationAdmin(admin.ModelAdmin):
    """Admin configuration for MarketCorrelation model"""
    
    list_display = [
        'date', 'correlation_30d', 'correlation_7d', 
        'correlation_strength_30d', 'sp500_return', 'ibovespa_return'
    ]
    list_filter = ['date']
    ordering = ['-date']
    date_hierarchy = 'date'
    
    def correlation_strength_30d(self, obj):
        strength = obj.correlation_strength_30d
        color_map = {
            'high': 'red',
            'medium': 'orange', 
            'low': 'green'
        }
        color = color_map.get(strength, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, strength.upper()
        )
    correlation_strength_30d.short_description = 'Strength (30d)'


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    """Admin configuration for ExchangeRate model"""
    
    list_display = ['date', 'rate', 'source', 'created_at']
    list_filter = ['source', 'date']
    ordering = ['-date']
    date_hierarchy = 'date'


@admin.register(APIUsageLog)
class APIUsageLogAdmin(admin.ModelAdmin):
    """Admin configuration for APIUsageLog model"""
    
    list_display = [
        'user', 'endpoint', 'method', 'status_code', 
        'response_time_ms', 'ip_address', 'timestamp'
    ]
    list_filter = [
        'method', 'status_code', 'endpoint', 'timestamp'
    ]
    search_fields = ['user__username', 'endpoint', 'ip_address']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    # Make all fields read-only since this is a log
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


# Customize admin site
admin.site.site_header = "Brazilian Financial API Admin"
admin.site.site_title = "Financial API Admin"
admin.site.index_title = "Welcome to Financial API Administration"
