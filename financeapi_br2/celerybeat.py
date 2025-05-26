from celery.schedules import crontab
from celery import Celery

app = Celery('financeapi_br2')

app.conf.beat_schedule = {
    # Update ADR quotes every 5 minutes during market hours
    'update-adr-quotes': {
        'task': 'financial_api.tasks.update_adr_quotes',
        'schedule': 300.0,  # 5 minutes
    },
    
    # Check price alerts every minute
    'check-price-alerts': {
        'task': 'financial_api.tasks.check_price_alerts',
        'schedule': 60.0,  # 1 minute
    },
    
    # Update correlation data every hour
    'update-correlation-data': {
        'task': 'financial_api.tasks.update_correlation_data',
        'schedule': 3600.0,  # 1 hour
    },
    
    # Update exchange rates every 30 minutes
    'update-exchange-rates': {
        'task': 'financial_api.tasks.update_exchange_rates',
        'schedule': 1800.0,  # 30 minutes
    },
    
    # Daily portfolio snapshots at 6 PM São Paulo time
    'daily-portfolio-snapshot': {
        'task': 'financial_api.tasks.daily_portfolio_snapshot',
        'schedule': crontab(hour=18, minute=0, tz='America/Sao_Paulo'),
    },
    
    # Reset daily request counters at midnight
    'reset-daily-request-counters': {
        'task': 'financial_api.tasks.reset_daily_request_counters',
        'schedule': crontab(hour=0, minute=0, tz='America/Sao_Paulo'),
    },
    
    # Clean up old data weekly
    'cleanup-old-data': {
        'task': 'financial_api.tasks.cleanup_old_data',
        'schedule': crontab(hour=1, minute=0, day_of_week='monday'),
    },
    
    # Send daily market summary to premium users
    'send-daily-market-summary': {
        'task': 'financial_api.tasks.send_daily_market_summary',
        'schedule': crontab(hour=18, minute=30, tz='America/Sao_Paulo'),
    },
    
    # Health check every 5 minutes
    'health-check': {
        'task': 'financial_api.tasks.health_check',
        'schedule': 300.0,  # 5 minutes
    },
}

# Timezone for beat schedule
app.conf.timezone = 'America/Sao_Paulo' 