from rest_framework import serializers
from decimal import Decimal
from .models import (
    User, ADRQuote, PriceAlert, Portfolio, Transaction, 
    MarketCorrelation, ExchangeRate, APIUsageLog
)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'plan', 'daily_requests', 'created_at'
        ]
        read_only_fields = ['id', 'daily_requests', 'created_at']


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'password', 'password_confirm'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ADRQuoteSerializer(serializers.ModelSerializer):
    """Serializer for ADR quotes"""
    
    change_percent_day_formatted = serializers.SerializerMethodField()
    price_usd_formatted = serializers.SerializerMethodField()
    price_brl_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = ADRQuote
        fields = [
            'ticker', 'price_usd', 'price_brl', 'exchange_rate',
            'volume', 'change_percent_day', 'timestamp', 'source',
            'delay_minutes', 'change_percent_day_formatted',
            'price_usd_formatted', 'price_brl_formatted'
        ]
    
    def get_change_percent_day_formatted(self, obj):
        """Format change percentage with + or - sign"""
        if obj.change_percent_day is None:
            return "0.00%"
        
        change = float(obj.change_percent_day)
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.2f}%"
    
    def get_price_usd_formatted(self, obj):
        """Format USD price with currency symbol"""
        return f"${obj.price_usd:.2f}"
    
    def get_price_brl_formatted(self, obj):
        """Format BRL price with currency symbol"""
        return f"R${obj.price_brl:.2f}"


class ADRQuoteResponseSerializer(serializers.Serializer):
    """Serializer for ADR quote API response"""
    
    ticker = serializers.CharField()
    price_usd = serializers.DecimalField(max_digits=10, decimal_places=4)
    price_brl = serializers.DecimalField(max_digits=10, decimal_places=4)
    exchange_rate = serializers.DecimalField(max_digits=8, decimal_places=4)
    change_percent_day = serializers.CharField()
    volume = serializers.IntegerField()
    timestamp = serializers.DateTimeField()
    source = serializers.CharField()
    delay_minutes = serializers.IntegerField()


class PriceAlertSerializer(serializers.ModelSerializer):
    """Serializer for price alerts"""
    
    class Meta:
        model = PriceAlert
        fields = [
            'id', 'ticker', 'condition_type', 'target_value',
            'notification_channel', 'webhook_url', 'is_active',
            'triggered_at', 'created_at'
        ]
        read_only_fields = ['id', 'triggered_at', 'created_at']
    
    def validate_ticker(self, value):
        """Validate that ticker is a supported ADR"""
        from django.conf import settings
        supported_adrs = getattr(settings, 'SUPPORTED_ADRS', [])
        
        if value.upper() not in supported_adrs:
            raise serializers.ValidationError(
                f"Ticker {value} is not supported. Supported ADRs: {', '.join(supported_adrs)}"
            )
        
        return value.upper()
    
    def validate_target_value(self, value):
        """Validate target value is positive"""
        if value <= 0:
            raise serializers.ValidationError("Target value must be positive")
        return value
    
    def validate(self, attrs):
        """Validate webhook URL is provided for webhook notifications"""
        if attrs.get('notification_channel') == 'webhook' and not attrs.get('webhook_url'):
            raise serializers.ValidationError(
                "Webhook URL is required for webhook notifications"
            )
        return attrs


class PortfolioSerializer(serializers.ModelSerializer):
    """Serializer for portfolio holdings"""
    
    current_value_usd = serializers.ReadOnlyField()
    current_value_brl = serializers.ReadOnlyField()
    gain_loss_usd = serializers.ReadOnlyField()
    gain_loss_percent = serializers.ReadOnlyField()
    current_price_usd = serializers.SerializerMethodField()
    current_price_brl = serializers.SerializerMethodField()
    
    class Meta:
        model = Portfolio
        fields = [
            'id', 'ticker', 'quantity', 'average_price_usd',
            'current_value_usd', 'current_value_brl', 'gain_loss_usd',
            'gain_loss_percent', 'current_price_usd', 'current_price_brl',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_current_price_usd(self, obj):
        """Get current USD price for the ticker"""
        try:
            latest_quote = ADRQuote.objects.filter(ticker=obj.ticker).first()
            return latest_quote.price_usd if latest_quote else None
        except:
            return None
    
    def get_current_price_brl(self, obj):
        """Get current BRL price for the ticker"""
        try:
            latest_quote = ADRQuote.objects.filter(ticker=obj.ticker).first()
            return latest_quote.price_brl if latest_quote else None
        except:
            return None
    
    def validate_ticker(self, value):
        """Validate that ticker is a supported ADR"""
        from django.conf import settings
        supported_adrs = getattr(settings, 'SUPPORTED_ADRS', [])
        
        if value.upper() not in supported_adrs:
            raise serializers.ValidationError(
                f"Ticker {value} is not supported. Supported ADRs: {', '.join(supported_adrs)}"
            )
        
        return value.upper()


class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for transactions"""
    
    total_value_usd = serializers.ReadOnlyField()
    total_value_brl = serializers.ReadOnlyField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'ticker', 'transaction_type', 'quantity', 'price_usd',
            'exchange_rate', 'date', 'brokerage_fee', 'total_value_usd',
            'total_value_brl', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate_ticker(self, value):
        """Validate that ticker is a supported ADR"""
        from django.conf import settings
        supported_adrs = getattr(settings, 'SUPPORTED_ADRS', [])
        
        if value.upper() not in supported_adrs:
            raise serializers.ValidationError(
                f"Ticker {value} is not supported. Supported ADRs: {', '.join(supported_adrs)}"
            )
        
        return value.upper()


class MarketCorrelationSerializer(serializers.ModelSerializer):
    """Serializer for market correlation data"""
    
    correlation_strength_30d = serializers.ReadOnlyField()
    correlation_strength_7d = serializers.ReadOnlyField()
    
    class Meta:
        model = MarketCorrelation
        fields = [
            'date', 'correlation_30d', 'correlation_7d', 'sp500_return',
            'ibovespa_return', 'correlation_strength_30d', 'correlation_strength_7d'
        ]


class CorrelationResponseSerializer(serializers.Serializer):
    """Serializer for correlation API response"""
    
    date = serializers.DateField()
    correlation_30d = serializers.DecimalField(max_digits=5, decimal_places=4)
    correlation_7d = serializers.DecimalField(max_digits=5, decimal_places=4)
    correlation_strength_30d = serializers.CharField()
    correlation_strength_7d = serializers.CharField()
    sp500_return = serializers.DecimalField(max_digits=6, decimal_places=4)
    ibovespa_return = serializers.DecimalField(max_digits=6, decimal_places=4)
    insights = serializers.ListField(child=serializers.CharField())
    trend_analysis = serializers.DictField()


class TaxCalculationRequestSerializer(serializers.Serializer):
    """Serializer for tax calculation request"""
    
    transactions = TransactionSerializer(many=True)
    year = serializers.IntegerField(min_value=2020, max_value=2030)
    
    def validate_year(self, value):
        """Validate year is reasonable"""
        from datetime import datetime
        current_year = datetime.now().year
        
        if value > current_year:
            raise serializers.ValidationError("Year cannot be in the future")
        
        return value


class TaxCalculationResponseSerializer(serializers.Serializer):
    """Serializer for tax calculation response"""
    
    year = serializers.IntegerField()
    total_gains = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_losses = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_gains = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_owed = serializers.DecimalField(max_digits=12, decimal_places=2)
    monthly_breakdown = serializers.ListField()
    recommendations = serializers.ListField(child=serializers.CharField())


class DashboardResponseSerializer(serializers.Serializer):
    """Serializer for dashboard API response"""
    
    portfolio_summary = serializers.DictField()
    dollar_impact = serializers.DictField()
    top_performers = serializers.ListField()
    market_overview = serializers.DictField()
    alerts_summary = serializers.DictField()
    recommendations = serializers.ListField(child=serializers.CharField())


class ExchangeRateSerializer(serializers.ModelSerializer):
    """Serializer for exchange rates"""
    
    class Meta:
        model = ExchangeRate
        fields = ['date', 'rate', 'source', 'created_at']


class APIUsageLogSerializer(serializers.ModelSerializer):
    """Serializer for API usage logs"""
    
    class Meta:
        model = APIUsageLog
        fields = [
            'endpoint', 'method', 'status_code', 'response_time_ms',
            'ip_address', 'timestamp'
        ]


class ErrorResponseSerializer(serializers.Serializer):
    """Serializer for error responses"""
    
    error = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)
    timestamp = serializers.DateTimeField()


class SuccessResponseSerializer(serializers.Serializer):
    """Serializer for success responses"""
    
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = serializers.DictField(required=False) 