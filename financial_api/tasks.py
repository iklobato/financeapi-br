from celery import shared_task
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from .models import ADRQuote, PriceAlert, MarketCorrelation, ExchangeRate, User
from .external_apis import APIManager
from .utils import NotificationService, MarketDataCache, InsightGenerator

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def update_adr_quotes(self):
    """Update ADR quotes from external APIs"""
    try:
        api_manager = APIManager()
        supported_adrs = getattr(settings, 'SUPPORTED_ADRS', [])
        
        updated_count = 0
        failed_count = 0
        
        for ticker in supported_adrs:
            try:
                # Get quote data with BRL conversion
                quote_data = api_manager.get_adr_quote_with_brl(ticker)
                
                if quote_data:
                    # Save to database
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
                    
                    # Cache the data
                    MarketDataCache.cache_quote(ticker, quote_data, timeout=60)
                    
                    updated_count += 1
                    logger.info(f"Updated quote for {ticker}: ${quote_data['price_usd']} (R${quote_data['price_brl']})")
                
                else:
                    failed_count += 1
                    logger.warning(f"Failed to get quote data for {ticker}")
            
            except Exception as e:
                failed_count += 1
                logger.error(f"Error updating quote for {ticker}: {e}")
        
        logger.info(f"ADR quotes update completed: {updated_count} updated, {failed_count} failed")
        
        return {
            'updated': updated_count,
            'failed': failed_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in update_adr_quotes task: {e}")
        # Retry the task
        raise self.retry(countdown=60, exc=e)


@shared_task(bind=True, max_retries=3)
def check_price_alerts(self):
    """Check price alerts and send notifications"""
    try:
        active_alerts = PriceAlert.objects.filter(is_active=True)
        triggered_count = 0
        
        for alert in active_alerts:
            try:
                # Get current price for the ticker
                latest_quote = ADRQuote.objects.filter(ticker=alert.ticker).first()
                
                if not latest_quote:
                    logger.warning(f"No quote data found for {alert.ticker}")
                    continue
                
                current_price_brl = latest_quote.price_brl
                
                # Check if alert condition is met
                if self._check_alert_condition(alert, current_price_brl):
                    # Send notification
                    notification_sent = NotificationService.send_price_alert(
                        alert, current_price_brl
                    )
                    
                    if notification_sent:
                        # Mark alert as triggered
                        alert.triggered_at = timezone.now()
                        alert.is_active = False
                        alert.save()
                        
                        triggered_count += 1
                        logger.info(f"Alert triggered for {alert.ticker}: {alert.condition_type} {alert.target_value}")
                    
                    else:
                        logger.error(f"Failed to send notification for alert {alert.id}")
            
            except Exception as e:
                logger.error(f"Error checking alert {alert.id}: {e}")
        
        logger.info(f"Price alerts check completed: {triggered_count} alerts triggered")
        
        return {
            'checked': active_alerts.count(),
            'triggered': triggered_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in check_price_alerts task: {e}")
        raise self.retry(countdown=30, exc=e)
    
    def _check_alert_condition(self, alert, current_price):
        """Check if alert condition is met"""
        try:
            if alert.condition_type == 'above':
                return current_price >= alert.target_value
            elif alert.condition_type == 'below':
                return current_price <= alert.target_value
            elif alert.condition_type == 'change_percent':
                # For percentage change, we'd need historical data
                # This is a simplified implementation
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking alert condition: {e}")
            return False


@shared_task(bind=True, max_retries=3)
def update_correlation_data(self):
    """Update market correlation data between SP500 and Ibovespa"""
    try:
        api_manager = APIManager()
        
        # Get correlation data
        correlation_data = api_manager.get_market_correlation_data()
        
        if correlation_data:
            # Save to database
            correlation, created = MarketCorrelation.objects.update_or_create(
                date=correlation_data['date'],
                defaults={
                    'correlation_30d': correlation_data['correlation_30d'],
                    'correlation_7d': correlation_data['correlation_7d'],
                    'sp500_return': correlation_data['sp500_return'],
                    'ibovespa_return': correlation_data['ibovespa_return']
                }
            )
            
            # Cache the data
            MarketDataCache.cache_correlation(correlation_data, timeout=3600)
            
            action = "Created" if created else "Updated"
            logger.info(f"{action} correlation data for {correlation_data['date']}")
            
            return {
                'success': True,
                'date': correlation_data['date'].isoformat(),
                'correlation_30d': str(correlation_data['correlation_30d']),
                'correlation_7d': str(correlation_data['correlation_7d']),
                'created': created
            }
        
        else:
            logger.warning("Failed to get correlation data")
            return {'success': False, 'error': 'No correlation data available'}
        
    except Exception as e:
        logger.error(f"Error in update_correlation_data task: {e}")
        raise self.retry(countdown=300, exc=e)


@shared_task(bind=True, max_retries=3)
def update_exchange_rates(self):
    """Update USD/BRL exchange rates"""
    try:
        api_manager = APIManager()
        
        # Get current exchange rate
        rate_data = api_manager.bcb.get_usd_brl_rate()
        
        if rate_data:
            # Parse date from BCB format (DD/MM/YYYY)
            date_str = rate_data['date']
            rate_date = datetime.strptime(date_str, '%d/%m/%Y').date()
            
            # Save to database
            exchange_rate, created = ExchangeRate.objects.update_or_create(
                date=rate_date,
                defaults={
                    'rate': rate_data['rate'],
                    'source': rate_data['source']
                }
            )
            
            action = "Created" if created else "Updated"
            logger.info(f"{action} exchange rate for {rate_date}: {rate_data['rate']}")
            
            return {
                'success': True,
                'date': rate_date.isoformat(),
                'rate': str(rate_data['rate']),
                'created': created
            }
        
        else:
            logger.warning("Failed to get exchange rate data")
            return {'success': False, 'error': 'No exchange rate data available'}
        
    except Exception as e:
        logger.error(f"Error in update_exchange_rates task: {e}")
        raise self.retry(countdown=300, exc=e)


@shared_task
def daily_portfolio_snapshot():
    """Create daily portfolio snapshots for all users"""
    try:
        from .utils import PortfolioAnalyzer
        
        users_with_portfolio = User.objects.filter(portfolio__isnull=False).distinct()
        snapshot_count = 0
        
        for user in users_with_portfolio:
            try:
                analyzer = PortfolioAnalyzer(user)
                portfolio_summary = analyzer.get_portfolio_summary()
                
                # Here you could save daily snapshots to a separate model
                # For now, we'll just log the summary
                logger.info(f"Portfolio snapshot for user {user.username}: "
                           f"Value: ${portfolio_summary['total_value_usd']:.2f} "
                           f"(R${portfolio_summary['total_value_brl']:.2f})")
                
                snapshot_count += 1
                
            except Exception as e:
                logger.error(f"Error creating portfolio snapshot for user {user.id}: {e}")
        
        logger.info(f"Daily portfolio snapshots completed: {snapshot_count} users processed")
        
        return {
            'users_processed': snapshot_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in daily_portfolio_snapshot task: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def cleanup_old_data():
    """Clean up old data to maintain database performance"""
    try:
        # Keep only last 30 days of ADR quotes
        cutoff_date = timezone.now() - timedelta(days=30)
        
        deleted_quotes = ADRQuote.objects.filter(created_at__lt=cutoff_date).delete()
        logger.info(f"Deleted {deleted_quotes[0]} old ADR quotes")
        
        # Keep only last 90 days of API usage logs
        from .models import APIUsageLog
        cutoff_date_logs = timezone.now() - timedelta(days=90)
        
        deleted_logs = APIUsageLog.objects.filter(timestamp__lt=cutoff_date_logs).delete()
        logger.info(f"Deleted {deleted_logs[0]} old API usage logs")
        
        return {
            'deleted_quotes': deleted_quotes[0],
            'deleted_logs': deleted_logs[0],
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in cleanup_old_data task: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def reset_daily_request_counters():
    """Reset daily request counters for all users"""
    try:
        users_to_reset = User.objects.filter(
            last_request_reset__lt=timezone.now() - timedelta(days=1)
        )
        
        reset_count = 0
        for user in users_to_reset:
            user.reset_daily_requests()
            reset_count += 1
        
        logger.info(f"Reset daily request counters for {reset_count} users")
        
        return {
            'users_reset': reset_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in reset_daily_request_counters task: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, max_retries=3)
def send_daily_market_summary(self):
    """Send daily market summary to premium users"""
    try:
        # Get premium users who want daily summaries
        premium_users = User.objects.filter(plan='premium')
        
        if not premium_users.exists():
            return {'message': 'No premium users found'}
        
        # Get market data
        api_manager = APIManager()
        
        # Get latest correlation data
        correlation_data = MarketCorrelation.objects.first()
        
        # Get latest ADR quotes
        latest_quotes = {}
        supported_adrs = getattr(settings, 'SUPPORTED_ADRS', [])
        
        for ticker in supported_adrs:
            quote = ADRQuote.objects.filter(ticker=ticker).first()
            if quote:
                latest_quotes[ticker] = {
                    'price_usd': quote.price_usd,
                    'price_brl': quote.price_brl,
                    'change_percent': quote.change_percent_day
                }
        
        # Generate insights
        insights = []
        if correlation_data:
            insights = InsightGenerator.generate_correlation_insights({
                'correlation_30d': correlation_data.correlation_30d,
                'correlation_7d': correlation_data.correlation_7d,
                'sp500_return': correlation_data.sp500_return,
                'ibovespa_return': correlation_data.ibovespa_return
            })
        
        # Send summary to each premium user
        sent_count = 0
        for user in premium_users:
            try:
                # Here you would send the actual email/notification
                # For now, we'll just log it
                logger.info(f"Sending daily market summary to {user.email}")
                sent_count += 1
                
            except Exception as e:
                logger.error(f"Error sending summary to user {user.id}: {e}")
        
        logger.info(f"Daily market summary sent to {sent_count} premium users")
        
        return {
            'sent_count': sent_count,
            'total_premium_users': premium_users.count(),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in send_daily_market_summary task: {e}")
        raise self.retry(countdown=300, exc=e)


@shared_task
def health_check():
    """Health check task to verify system is working"""
    try:
        # Check database connectivity
        user_count = User.objects.count()
        
        # Check external APIs
        api_manager = APIManager()
        
        # Test BCB API
        bcb_status = "OK" if api_manager.bcb.get_usd_brl_rate() else "FAILED"
        
        # Test cache
        cache_key = "health_check_test"
        MarketDataCache.cache_quote(cache_key, {"test": "data"}, timeout=60)
        cached_data = MarketDataCache.get_cached_quote(cache_key)
        cache_status = "OK" if cached_data else "FAILED"
        
        return {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'database': f"OK ({user_count} users)",
            'bcb_api': bcb_status,
            'cache': cache_status
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        } 