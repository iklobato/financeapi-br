# Brazilian Financial API (financeapi-br)

A comprehensive REST API for Brazilian ADR (American Depositary Receipt) market data, exchange rates, and portfolio management, with a focus on Brazilian investors tracking their international investments.

## Features

- Real-time ADR quotes with USD and BRL prices
- Exchange rate tracking (USD/BRL)
- Portfolio management with tax calculations
- Market correlation analysis (S&P 500 vs Ibovespa)
- Price alerts and notifications
- Historical data and performance metrics
- Automated tasks for data updates and maintenance

## Tech Stack

- **Framework**: Django 4.2.21 with Django REST Framework
- **Database**: PostgreSQL (with SQLite support for development)
- **Cache**: Redis
- **Task Queue**: Celery with Redis broker
- **External APIs**:
  - Polygon.io for ADR data
  - Brazilian Central Bank (BCB) for exchange rates
  - Yahoo Finance for market indices

## Architecture

### Core Components

1. **API Layer**
   - RESTful endpoints with authentication
   - Rate limiting based on subscription plans
   - Comprehensive error handling and logging

2. **Data Services**
   - Real-time market data integration
   - Caching strategy for performance optimization
   - Historical data management

3. **Background Tasks**
   - Automated data updates
   - Price alert monitoring
   - Portfolio snapshots and analytics

4. **Security**
   - API key authentication
   - HTTPS enforcement in production
   - Rate limiting and request validation

## API Endpoints

### ADR Quotes

```http
GET /api/adr/quote/{ticker}/
```
Get real-time ADR quote with USD and BRL prices.

Parameters:
- `ticker`: ADR symbol (e.g., 'VALE', 'PBR')

Response:
```json
{
    "ticker": "VALE",
    "price_usd": 15.75,
    "price_brl": 78.75,
    "exchange_rate": 5.00,
    "volume": 12345678,
    "change_percent_day": -1.25,
    "timestamp": "2025-05-25T14:30:00Z",
    "source": "polygon",
    "delay_minutes": 15
}
```

### Market Correlation

```http
GET /api/correlacao/ibovespa-sp500/
```
Get correlation analysis between S&P 500 and Ibovespa.

Response:
```json
{
    "date": "2025-05-25",
    "correlation_30d": 0.85,
    "correlation_7d": 0.78,
    "correlation_strength_30d": "high",
    "correlation_strength_7d": "high",
    "sp500_return": 1.25,
    "ibovespa_return": 1.15,
    "insights": [
        "Strong positive correlation in the last 30 days",
        "Markets moving in tandem with similar returns"
    ]
}
```

### Portfolio Management

```http
POST /api/portfolio/transaction/
```
Record a new portfolio transaction.

Request:
```json
{
    "ticker": "VALE",
    "type": "BUY",
    "quantity": 100,
    "price_usd": 15.75,
    "date": "2025-05-25",
    "exchange_rate": 5.00
}
```

```http
GET /api/portfolio/summary/
```
Get portfolio summary with performance metrics.

Response:
```json
{
    "total_value_usd": 50000.00,
    "total_value_brl": 250000.00,
    "total_return_pct": 15.75,
    "holdings": [
        {
            "ticker": "VALE",
            "quantity": 1000,
            "current_value_usd": 15750.00,
            "current_value_brl": 78750.00,
            "weight": 0.315
        }
    ]
}
```

### Price Alerts

```http
POST /api/alerts/
```
Create a new price alert.

Request:
```json
{
    "ticker": "VALE",
    "price_usd": 16.00,
    "condition": "above",
    "notification_type": "email"
}
```

## Background Tasks

### Scheduled Tasks

1. **update_adr_quotes**
   - Frequency: Every minute during market hours
   - Updates quotes for all supported ADRs
   - Manages cache and database storage

2. **check_price_alerts**
   - Frequency: Every minute
   - Checks active price alerts against current quotes
   - Triggers notifications when conditions are met

3. **update_correlation_data**
   - Frequency: Every hour
   - Calculates market correlations
   - Updates historical correlation data

4. **daily_portfolio_snapshot**
   - Frequency: Daily after market close
   - Records portfolio values and performance
   - Generates daily reports

### Maintenance Tasks

1. **cleanup_old_data**
   - Frequency: Daily
   - Removes outdated quotes and historical data
   - Maintains database performance

2. **health_check**
   - Frequency: Every minute
   - Monitors API services and connections
   - Reports issues to monitoring system

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/iklobato/financeapi-br.git
cd financeapi-br
```

2. Create and activate virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
python -m pip install uv
uv pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Start services:
```bash
redis-server
celery -A financeapi_br2 worker -l info
celery -A financeapi_br2 beat -l info
python manage.py runserver
```

## Production Deployment

### Requirements

- PostgreSQL database
- Redis server
- HTTPS certificate
- Monitoring system
- Sufficient API quotas for external services

### Configuration

1. Set secure environment variables:
   - `SECRET_KEY`
   - `ALLOWED_HOSTS`
   - `DATABASE_URL`
   - `REDIS_URL`
   - `POLYGON_API_KEY`

2. Enable production settings:
   - HTTPS enforcement
   - Proper CORS configuration
   - Rate limiting
   - Secure cookie settings

3. Set up monitoring:
   - Application logs
   - Error tracking
   - Performance metrics
   - API usage monitoring

## Challenges and Solutions

1. **Real-time Data Synchronization**
   - Challenge: Maintaining consistent and timely market data
   - Solution: Implemented efficient caching with Redis and background tasks

2. **Exchange Rate Management**
   - Challenge: Accurate currency conversion for Brazilian investors
   - Solution: Direct integration with Brazilian Central Bank API and fallback sources

3. **Performance Optimization**
   - Challenge: Handling multiple concurrent requests and data updates
   - Solution: Implemented caching strategies and database optimizations

4. **API Rate Limits**
   - Challenge: Managing external API quotas and costs
   - Solution: Implemented tiered rate limiting and efficient data caching

## Future Improvements

1. **Technical Analysis**
   - Add technical indicators and chart patterns
   - Implement trading signals

2. **Machine Learning Integration**
   - Portfolio optimization suggestions
   - Market trend predictions

3. **Enhanced Reporting**
   - Custom report generation
   - Tax documentation for Brazilian investors

4. **Mobile App Integration**
   - Real-time push notifications
   - Mobile-optimized endpoints

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, email support@financeapi-br.com.br or open an issue in the repository.

## Acknowledgments

- Polygon.io for market data
- Brazilian Central Bank for exchange rates
- Yahoo Finance for market indices
- All contributors and users of the API # financeapi-br
