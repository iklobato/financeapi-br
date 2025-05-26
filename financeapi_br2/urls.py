"""
URL configuration for financeapi_br2 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.utils import timezone

def api_root(request):
    """API root endpoint with documentation"""
    return JsonResponse({
        'message': 'Brazilian Financial API - ADR Quotes & Analysis',
        'version': '1.0.0',
        'timestamp': timezone.now(),
        'endpoints': {
            'authentication': {
                'register': '/api/auth/register/',
                'profile': '/api/auth/profile/',
            },
            'adr_quotes': {
                'quote_brl': '/api/adrs/{ticker}/cotacao-brl/',
                'supported_adrs': '/api/adrs/supported/',
            },
            'market_analysis': {
                'correlation': '/api/correlacao/ibovespa-sp500/',
                'exchange_rate': '/api/cambio/usd-brl/',
            },
            'portfolio': {
                'portfolio': '/api/portfolio/',
                'dashboard': '/api/dashboard/impacto-dolar/',
            },
            'alerts': {
                'price_alerts': '/api/alertas/preco/',
            },
            'tax': {
                'calculator': '/api/calculadora/ir-adrs/',
            },
            'system': {
                'status': '/api/status/',
            }
        },
        'documentation': 'https://docs.financeapi.com.br',
        'support': 'support@financeapi.com.br'
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('financial_api.urls')),
    path('api/', api_root, name='api_root'),
    path('', api_root, name='home'),
]
