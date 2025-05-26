from django.urls import path, include
from . import views

app_name = 'financial_api'

urlpatterns = [
    # User management
    path('auth/register/', views.UserRegistrationView.as_view(), name='user_register'),
    path('auth/profile/', views.UserProfileView.as_view(), name='user_profile'),
    
    # ADR quotes
    path('adrs/<str:ticker>/cotacao-brl/', views.adr_quote_brl, name='adr_quote_brl'),
    path('adrs/supported/', views.supported_adrs, name='supported_adrs'),
    
    # Market correlation
    path('correlacao/ibovespa-sp500/', views.market_correlation, name='market_correlation'),
    
    # Price alerts
    path('alertas/preco/', views.PriceAlertViewSet.as_view(), name='price_alerts'),
    path('alertas/preco/<uuid:alert_id>/', views.PriceAlertViewSet.as_view(), name='price_alert_detail'),
    
    # Portfolio management
    path('portfolio/', views.PortfolioViewSet.as_view(), name='portfolio'),
    
    # Tax calculator
    path('calculadora/ir-adrs/', views.tax_calculator, name='tax_calculator'),
    
    # Dashboard
    path('dashboard/impacto-dolar/', views.dashboard_dollar_impact, name='dashboard_dollar_impact'),
    
    # Exchange rate
    path('cambio/usd-brl/', views.exchange_rate, name='exchange_rate'),
    
    # System status
    path('status/', views.api_status, name='api_status'),
] 