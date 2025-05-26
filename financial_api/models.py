from django.db import models
import uuid
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from cryptography.fernet import Fernet
from django.conf import settings
import secrets


class User(AbstractUser):
    """Extended User model with API key and plan management"""
    
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('premium', 'Premium'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default='free')
    api_key = models.CharField(max_length=64, unique=True, blank=True)
    daily_requests = models.IntegerField(default=0)
    last_request_reset = models.DateTimeField(default=timezone.now)
    whatsapp_number = models.CharField(max_length=20, blank=True, null=True, help_text="WhatsApp number in international format (e.g., +5511999999999)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Override groups and user_permissions with custom related_names
    groups = models.ManyToManyField(
        'auth.Group',
        blank=True,
        related_name='financial_api_users',
        related_query_name='financial_api_user',
        help_text='The groups this user belongs to.'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        related_name='financial_api_users',
        related_query_name='financial_api_user',
        help_text='Specific permissions for this user.'
    )
    
    class Meta:
        db_table = 'financial_api_user'
    
    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = self.generate_api_key()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_api_key():
        """Generate a secure API key"""
        return f"fa_{secrets.token_urlsafe(32)}"
    
    def reset_daily_requests(self):
        """Reset daily request counter"""
        self.daily_requests = 0
        self.last_request_reset = timezone.now()
        self.save(update_fields=['daily_requests', 'last_request_reset'])
    
    def can_make_request(self):
        """Check if user can make another API request based on their plan"""
        # Reset counter if it's a new day
        if (timezone.now() - self.last_request_reset).days >= 1:
            self.reset_daily_requests()
        
        plan_limits = getattr(settings, 'RATE_LIMIT_PLANS', {})
        limit = plan_limits.get(self.plan)
        
        if limit is None:  # Unlimited for premium
            return True
        
        return self.daily_requests < limit
    
    def increment_requests(self):
        """Increment the daily request counter"""
        self.daily_requests += 1
        self.save(update_fields=['daily_requests'])


class ADRQuote(models.Model):
    """Store ADR quotes with USD and BRL prices"""
    
    ticker = models.CharField(max_length=10, db_index=True)
    price_usd = models.DecimalField(
        max_digits=10, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    price_brl = models.DecimalField(
        max_digits=10, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    exchange_rate = models.DecimalField(
        max_digits=8, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    volume = models.BigIntegerField(default=0)
    change_percent_day = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    timestamp = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=20, default='polygon')
    delay_minutes = models.IntegerField(default=15)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'financial_api_adr_quote'
        indexes = [
            models.Index(fields=['ticker', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.ticker} - ${self.price_usd} (R${self.price_brl})"


class PriceAlert(models.Model):
    """Price alerts for ADR stocks"""
    
    CONDITION_CHOICES = [
        ('above', 'Above'),
        ('below', 'Below'),
        ('change_percent', 'Change Percent'),
    ]
    
    NOTIFICATION_CHOICES = [
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'),
        ('webhook', 'Webhook'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='price_alerts')
    ticker = models.CharField(max_length=10)
    condition_type = models.CharField(max_length=15, choices=CONDITION_CHOICES)
    target_value = models.DecimalField(max_digits=10, decimal_places=4)
    notification_channel = models.CharField(max_length=10, choices=NOTIFICATION_CHOICES)
    webhook_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    triggered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'financial_api_price_alert'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['ticker', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.ticker} {self.condition_type} {self.target_value}"


class Portfolio(models.Model):
    """User portfolio holdings"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolio')
    ticker = models.CharField(max_length=10)
    quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))]
    )
    average_price_usd = models.DecimalField(
        max_digits=10, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'financial_api_portfolio'
        unique_together = ['user', 'ticker']
        indexes = [
            models.Index(fields=['user', 'ticker']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.ticker}: {self.quantity} shares"
    
    @property
    def current_value_usd(self):
        """Calculate current value in USD"""
        try:
            latest_quote = ADRQuote.objects.filter(ticker=self.ticker).first()
            if latest_quote:
                return self.quantity * latest_quote.price_usd
        except ADRQuote.DoesNotExist:
            pass
        return Decimal('0.00')
    
    @property
    def current_value_brl(self):
        """Calculate current value in BRL"""
        try:
            latest_quote = ADRQuote.objects.filter(ticker=self.ticker).first()
            if latest_quote:
                return self.quantity * latest_quote.price_brl
        except ADRQuote.DoesNotExist:
            pass
        return Decimal('0.00')
    
    @property
    def gain_loss_usd(self):
        """Calculate gain/loss in USD"""
        current_value = self.current_value_usd
        cost_basis = self.quantity * self.average_price_usd
        return current_value - cost_basis
    
    @property
    def gain_loss_percent(self):
        """Calculate gain/loss percentage"""
        cost_basis = self.quantity * self.average_price_usd
        if cost_basis > 0:
            return (self.gain_loss_usd / cost_basis) * 100
        return Decimal('0.00')


class Transaction(models.Model):
    """Transaction history for tax calculations"""
    
    TRANSACTION_TYPES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    ticker = models.CharField(max_length=10)
    transaction_type = models.CharField(max_length=4, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))]
    )
    price_usd = models.DecimalField(
        max_digits=10, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    exchange_rate = models.DecimalField(
        max_digits=8, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    date = models.DateField()
    brokerage_fee = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    encrypted_data = models.TextField(blank=True)  # For sensitive data
    is_day_trade = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'financial_api_transaction'
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['ticker', 'date']),
            models.Index(fields=['user', 'ticker', 'date']),
        ]
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.transaction_type.upper()} {self.quantity} {self.ticker}"
    
    @property
    def total_value_usd(self):
        """Total transaction value in USD including fees"""
        base_value = self.quantity * self.price_usd
        return base_value + self.brokerage_fee
    
    @property
    def total_value_brl(self):
        """Total transaction value in BRL including fees"""
        return self.total_value_usd * self.exchange_rate


class MarketCorrelation(models.Model):
    """Market correlation data between SP500 and Ibovespa"""
    
    date = models.DateField(unique=True, db_index=True)
    correlation_30d = models.DecimalField(
        max_digits=5, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('-1.0')), MaxValueValidator(Decimal('1.0'))]
    )
    correlation_7d = models.DecimalField(
        max_digits=5, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('-1.0')), MaxValueValidator(Decimal('1.0'))]
    )
    sp500_return = models.DecimalField(
        max_digits=6, 
        decimal_places=4,
        help_text="Daily return percentage"
    )
    ibovespa_return = models.DecimalField(
        max_digits=6, 
        decimal_places=4,
        help_text="Daily return percentage"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'financial_api_market_correlation'
        ordering = ['-date']
    
    def __str__(self):
        return f"Correlation {self.date}: 30d={self.correlation_30d}, 7d={self.correlation_7d}"
    
    @property
    def correlation_strength_30d(self):
        """Classify correlation strength for 30-day period"""
        abs_corr = abs(self.correlation_30d)
        if abs_corr >= 0.7:
            return "high"
        elif abs_corr >= 0.3:
            return "medium"
        else:
            return "low"
    
    @property
    def correlation_strength_7d(self):
        """Classify correlation strength for 7-day period"""
        abs_corr = abs(self.correlation_7d)
        if abs_corr >= 0.7:
            return "high"
        elif abs_corr >= 0.3:
            return "medium"
        else:
            return "low"


class ExchangeRate(models.Model):
    """Historical USD/BRL exchange rates"""
    
    date = models.DateField(unique=True, db_index=True)
    rate = models.DecimalField(
        max_digits=8, 
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    source = models.CharField(max_length=20, default='bcb')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'financial_api_exchange_rate'
        ordering = ['-date']
    
    def __str__(self):
        return f"USD/BRL {self.date}: {self.rate}"


class APIUsageLog(models.Model):
    """Log API usage for analytics and monitoring"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_logs')
    endpoint = models.CharField(max_length=100)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    response_time_ms = models.IntegerField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'financial_api_usage_log'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['endpoint', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.endpoint} ({self.status_code})"
