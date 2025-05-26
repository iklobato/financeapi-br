from django.shortcuts import render
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from datetime import datetime, date
from decimal import Decimal
import logging

from .models import (
    User, ADRQuote, PriceAlert, Portfolio, Transaction, 
    MarketCorrelation, ExchangeRate
)
from .serializers import (
    UserSerializer, UserRegistrationSerializer, ADRQuoteResponseSerializer,
    PriceAlertSerializer, PortfolioSerializer, TransactionSerializer,
    CorrelationResponseSerializer, TaxCalculationRequestSerializer,
    TaxCalculationResponseSerializer, DashboardResponseSerializer,
    ErrorResponseSerializer, SuccessResponseSerializer
)
from .external_apis import APIManager
from .utils import (
    TaxCalculator, PortfolioAnalyzer, MarketDataCache, 
    InsightGenerator, DataValidator
)

logger = logging.getLogger(__name__)


class UserRegistrationView(generics.CreateAPIView):
    """User registration endpoint"""
    
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Usuário criado com sucesso',
                'data': {
                    'user_id': str(user.id),
                    'username': user.username,
                    'api_key': user.api_key,
                    'plan': user.plan
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error in user registration: {e}")
            return Response({
                'error': 'Registration failed',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """User profile management"""
    
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def adr_quote_brl(request, ticker):
    """
    Get ADR quote in BRL
    GET /api/adrs/{ticker}/cotacao-brl/
    """
    try:
        # Validate ticker
        if not DataValidator.validate_ticker(ticker):
            return Response({
                'error': 'Invalid ticker',
                'message': f'Ticker {ticker} is not supported',
                'supported_tickers': settings.SUPPORTED_ADRS
            }, status=status.HTTP_400_BAD_REQUEST)
        
        ticker = ticker.upper()
        
        # Try to get from cache first
        cached_quote = MarketDataCache.get_cached_quote(ticker)
        if cached_quote:
            logger.info(f"Returning cached quote for {ticker}")
            return Response(cached_quote)
        
        # Get fresh data from APIs
        api_manager = APIManager()
        quote_data = api_manager.get_adr_quote_with_brl(ticker)
        
        if not quote_data:
            return Response({
                'error': 'Quote not available',
                'message': f'Unable to fetch quote for {ticker}',
                'ticker': ticker
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Save to database
        try:
            ADRQuote.objects.create(
                ticker=quote_data['ticker'],
                price_usd=quote_data['price_usd'],
                price_brl=quote_data['price_brl'],
                exchange_rate=quote_data['exchange_rate'],
                volume=quote_data['volume'],
                change_percent_day=quote_data['change_percent_day'],
                timestamp=quote_data['timestamp'],
                source=quote_data['source'],
                delay_minutes=quote_data['delay_minutes']
            )
        except Exception as e:
            logger.error(f"Error saving quote to database: {e}")
        
        # Cache the result
        MarketDataCache.cache_quote(ticker, quote_data, timeout=60)
        
        # Format response
        response_data = {
            'ticker': quote_data['ticker'],
            'price_usd': quote_data['price_usd'],
            'price_brl': quote_data['price_brl'],
            'exchange_rate': quote_data['exchange_rate'],
            'change_percent_day': f"+{quote_data['change_percent_day']:.2f}%" if quote_data['change_percent_day'] >= 0 else f"{quote_data['change_percent_day']:.2f}%",
            'volume': quote_data['volume'],
            'timestamp': quote_data['timestamp'],
            'source': quote_data['source'],
            'delay_minutes': quote_data['delay_minutes']
        }
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error in adr_quote_brl for {ticker}: {e}")
        return Response({
            'error': 'Internal server error',
            'message': 'Unable to process request'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def market_correlation(request):
    """
    Get market correlation between SP500 and Ibovespa
    GET /api/correlacao/ibovespa-sp500/
    """
    try:
        # Try to get from cache first
        cached_correlation = MarketDataCache.get_cached_correlation()
        if cached_correlation:
            logger.info("Returning cached correlation data")
            
            # Generate insights
            insights = InsightGenerator.generate_correlation_insights(cached_correlation)
            
            response_data = {
                'date': cached_correlation['date'],
                'correlation_30d': cached_correlation['correlation_30d'],
                'correlation_7d': cached_correlation['correlation_7d'],
                'correlation_strength_30d': 'high' if abs(float(cached_correlation['correlation_30d'])) >= 0.7 else 'medium' if abs(float(cached_correlation['correlation_30d'])) >= 0.3 else 'low',
                'correlation_strength_7d': 'high' if abs(float(cached_correlation['correlation_7d'])) >= 0.7 else 'medium' if abs(float(cached_correlation['correlation_7d'])) >= 0.3 else 'low',
                'sp500_return': cached_correlation['sp500_return'],
                'ibovespa_return': cached_correlation['ibovespa_return'],
                'insights': insights,
                'trend_analysis': {
                    'direction': 'positive' if float(cached_correlation['correlation_30d']) > 0 else 'negative',
                    'strength': 'strong' if abs(float(cached_correlation['correlation_30d'])) > 0.7 else 'moderate' if abs(float(cached_correlation['correlation_30d'])) > 0.3 else 'weak'
                }
            }
            
            return Response(response_data)
        
        # Get fresh correlation data
        api_manager = APIManager()
        correlation_data = api_manager.get_market_correlation_data()
        
        if not correlation_data:
            # Try to get latest from database
            latest_correlation = MarketCorrelation.objects.first()
            if latest_correlation:
                correlation_data = {
                    'date': latest_correlation.date,
                    'correlation_30d': latest_correlation.correlation_30d,
                    'correlation_7d': latest_correlation.correlation_7d,
                    'sp500_return': latest_correlation.sp500_return,
                    'ibovespa_return': latest_correlation.ibovespa_return
                }
            else:
                return Response({
                    'error': 'Correlation data not available',
                    'message': 'Unable to fetch correlation data'
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Save to database if fresh data
        if correlation_data and 'date' in correlation_data:
            try:
                MarketCorrelation.objects.update_or_create(
                    date=correlation_data['date'],
                    defaults={
                        'correlation_30d': correlation_data['correlation_30d'],
                        'correlation_7d': correlation_data['correlation_7d'],
                        'sp500_return': correlation_data['sp500_return'],
                        'ibovespa_return': correlation_data['ibovespa_return']
                    }
                )
            except Exception as e:
                logger.error(f"Error saving correlation to database: {e}")
        
        # Cache the result
        MarketDataCache.cache_correlation(correlation_data, timeout=3600)
        
        # Generate insights
        insights = InsightGenerator.generate_correlation_insights(correlation_data)
        
        # Format response
        response_data = {
            'date': correlation_data['date'],
            'correlation_30d': correlation_data['correlation_30d'],
            'correlation_7d': correlation_data['correlation_7d'],
            'correlation_strength_30d': 'high' if abs(float(correlation_data['correlation_30d'])) >= 0.7 else 'medium' if abs(float(correlation_data['correlation_30d'])) >= 0.3 else 'low',
            'correlation_strength_7d': 'high' if abs(float(correlation_data['correlation_7d'])) >= 0.7 else 'medium' if abs(float(correlation_data['correlation_7d'])) >= 0.3 else 'low',
            'sp500_return': correlation_data['sp500_return'],
            'ibovespa_return': correlation_data['ibovespa_return'],
            'insights': insights,
            'trend_analysis': {
                'direction': 'positive' if float(correlation_data['correlation_30d']) > 0 else 'negative',
                'strength': 'strong' if abs(float(correlation_data['correlation_30d'])) > 0.7 else 'moderate' if abs(float(correlation_data['correlation_30d'])) > 0.3 else 'weak'
            }
        }
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error in market_correlation: {e}")
        return Response({
            'error': 'Internal server error',
            'message': 'Unable to process correlation request'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PriceAlertViewSet(APIView):
    """Price alerts management"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """List user's price alerts"""
        try:
            alerts = PriceAlert.objects.filter(user=request.user)
            serializer = PriceAlertSerializer(alerts, many=True)
            
            return Response({
                'success': True,
                'count': alerts.count(),
                'alerts': serializer.data
            })
            
        except Exception as e:
            logger.error(f"Error listing price alerts for user {request.user.id}: {e}")
            return Response({
                'error': 'Unable to fetch alerts',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request):
        """Create new price alert"""
        try:
            # Check user's plan limits
            user_alerts_count = PriceAlert.objects.filter(user=request.user, is_active=True).count()
            
            plan_limits = {
                'free': 3,
                'pro': 20,
                'premium': 100
            }
            
            limit = plan_limits.get(request.user.plan, 3)
            
            if user_alerts_count >= limit:
                return Response({
                    'error': 'Alert limit exceeded',
                    'message': f'Your {request.user.plan} plan allows maximum {limit} active alerts',
                    'current_count': user_alerts_count,
                    'limit': limit
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer = PriceAlertSerializer(data=request.data)
            if serializer.is_valid():
                alert = serializer.save(user=request.user)
                
                return Response({
                    'success': True,
                    'message': 'Alerta criado com sucesso',
                    'alert': PriceAlertSerializer(alert).data
                }, status=status.HTTP_201_CREATED)
            
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error creating price alert for user {request.user.id}: {e}")
            return Response({
                'error': 'Unable to create alert',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request, alert_id):
        """Delete price alert"""
        try:
            alert = get_object_or_404(PriceAlert, id=alert_id, user=request.user)
            alert.delete()
            
            return Response({
                'success': True,
                'message': 'Alerta removido com sucesso'
            })
            
        except Exception as e:
            logger.error(f"Error deleting price alert {alert_id}: {e}")
            return Response({
                'error': 'Unable to delete alert',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PortfolioViewSet(APIView):
    """Portfolio management"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get user's portfolio"""
        try:
            analyzer = PortfolioAnalyzer(request.user)
            portfolio_summary = analyzer.get_portfolio_summary()
            
            return Response({
                'success': True,
                'portfolio': portfolio_summary
            })
            
        except Exception as e:
            logger.error(f"Error getting portfolio for user {request.user.id}: {e}")
            return Response({
                'error': 'Unable to fetch portfolio',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request):
        """Add/update portfolio holding"""
        try:
            serializer = PortfolioSerializer(data=request.data)
            if serializer.is_valid():
                ticker = serializer.validated_data['ticker']
                
                # Check if holding already exists
                holding, created = Portfolio.objects.get_or_create(
                    user=request.user,
                    ticker=ticker,
                    defaults=serializer.validated_data
                )
                
                if not created:
                    # Update existing holding (average price calculation)
                    new_quantity = serializer.validated_data['quantity']
                    new_price = serializer.validated_data['average_price_usd']
                    
                    total_cost = (holding.quantity * holding.average_price_usd) + (new_quantity * new_price)
                    total_quantity = holding.quantity + new_quantity
                    
                    holding.average_price_usd = total_cost / total_quantity
                    holding.quantity = total_quantity
                    holding.save()
                
                return Response({
                    'success': True,
                    'message': 'Posição atualizada com sucesso',
                    'holding': PortfolioSerializer(holding).data
                }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
            
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error updating portfolio for user {request.user.id}: {e}")
            return Response({
                'error': 'Unable to update portfolio',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def tax_calculator(request):
    """
    Calculate Brazilian taxes for ADR transactions
    POST /api/calculadora/ir-adrs/
    """
    try:
        serializer = TaxCalculationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        year = serializer.validated_data['year']
        transactions_data = serializer.validated_data['transactions']
        
        # Save transactions to database
        for transaction_data in transactions_data:
            Transaction.objects.create(
                user=request.user,
                **transaction_data
            )
        
        # Calculate taxes
        calculator = TaxCalculator(request.user, year)
        tax_result = calculator.calculate_taxes()
        
        return Response({
            'success': True,
            'tax_calculation': tax_result
        })
        
    except Exception as e:
        logger.error(f"Error in tax calculation for user {request.user.id}: {e}")
        return Response({
            'error': 'Tax calculation failed',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_dollar_impact(request):
    """
    Dollar impact dashboard
    GET /api/dashboard/impacto-dolar/
    """
    try:
        analyzer = PortfolioAnalyzer(request.user)
        
        # Get portfolio summary
        portfolio_summary = analyzer.get_portfolio_summary()
        
        # Calculate dollar impact
        dollar_impact = analyzer.calculate_dollar_impact()
        
        # Get top performers
        top_performers = analyzer.get_top_performers(limit=5)
        
        # Get market overview
        api_manager = APIManager()
        
        # Get latest correlation data
        correlation_data = MarketCorrelation.objects.first()
        market_overview = {}
        
        if correlation_data:
            market_overview = {
                'correlation_30d': correlation_data.correlation_30d,
                'correlation_strength': correlation_data.correlation_strength_30d,
                'sp500_return': correlation_data.sp500_return,
                'ibovespa_return': correlation_data.ibovespa_return
            }
        
        # Get alerts summary
        active_alerts = PriceAlert.objects.filter(user=request.user, is_active=True).count()
        triggered_alerts = PriceAlert.objects.filter(
            user=request.user, 
            triggered_at__date=date.today()
        ).count()
        
        alerts_summary = {
            'active_alerts': active_alerts,
            'triggered_today': triggered_alerts
        }
        
        # Generate recommendations
        recommendations = InsightGenerator.generate_portfolio_recommendations(
            portfolio_summary, market_overview
        )
        
        response_data = {
            'portfolio_summary': portfolio_summary,
            'dollar_impact': dollar_impact,
            'top_performers': top_performers,
            'market_overview': market_overview,
            'alerts_summary': alerts_summary,
            'recommendations': recommendations,
            'last_updated': timezone.now()
        }
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error in dashboard for user {request.user.id}: {e}")
        return Response({
            'error': 'Dashboard data unavailable',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def supported_adrs(request):
    """Get list of supported ADRs"""
    try:
        adrs = settings.SUPPORTED_ADRS
        
        # Get latest quotes for each ADR
        adr_data = []
        for ticker in adrs:
            latest_quote = ADRQuote.objects.filter(ticker=ticker).first()
            if latest_quote:
                adr_data.append({
                    'ticker': ticker,
                    'price_usd': latest_quote.price_usd,
                    'price_brl': latest_quote.price_brl,
                    'change_percent': latest_quote.change_percent_day,
                    'last_updated': latest_quote.timestamp
                })
            else:
                adr_data.append({
                    'ticker': ticker,
                    'price_usd': None,
                    'price_brl': None,
                    'change_percent': None,
                    'last_updated': None
                })
        
        return Response({
            'supported_adrs': adr_data,
            'count': len(adrs)
        })
        
    except Exception as e:
        logger.error(f"Error getting supported ADRs: {e}")
        return Response({
            'error': 'Unable to fetch ADR list',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def exchange_rate(request):
    """Get current USD/BRL exchange rate"""
    try:
        api_manager = APIManager()
        rate_data = api_manager.bcb.get_usd_brl_rate()
        
        if rate_data:
            return Response({
                'rate': rate_data['rate'],
                'date': rate_data['date'],
                'source': rate_data['source']
            })
        
        # Fallback to database
        latest_rate = ExchangeRate.objects.first()
        if latest_rate:
            return Response({
                'rate': latest_rate.rate,
                'date': latest_rate.date,
                'source': latest_rate.source
            })
        
        return Response({
            'error': 'Exchange rate not available',
            'message': 'Unable to fetch current exchange rate'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error getting exchange rate: {e}")
        return Response({
            'error': 'Exchange rate unavailable',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_status(request):
    """API health check endpoint"""
    try:
        # Check database
        user_count = User.objects.count()
        
        # Check cache
        cache.set('health_check', 'ok', 60)
        cache_status = cache.get('health_check') == 'ok'
        
        # Check external APIs
        api_manager = APIManager()
        bcb_status = api_manager.bcb.get_usd_brl_rate() is not None
        
        return Response({
            'status': 'healthy',
            'timestamp': timezone.now(),
            'services': {
                'database': f'OK ({user_count} users)',
                'cache': 'OK' if cache_status else 'FAILED',
                'bcb_api': 'OK' if bcb_status else 'FAILED'
            },
            'version': '1.0.0'
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now()
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
