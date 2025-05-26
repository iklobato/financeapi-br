# Brazilian Financial API (financeapi-br)

A comprehensive REST API for Brazilian ADR (American Depositary Receipt) market data, exchange rates, and portfolio management, with a focus on Brazilian investors tracking their international investments.

## Overview

This API provides a robust platform for Brazilian investors to:
- Track ADR prices in both USD and BRL in real-time
- Monitor exchange rates and currency exposure
- Manage investment portfolios with tax implications
- Analyze market correlations between Brazilian and US markets
- Set up price alerts and notifications
- Generate reports for tax purposes

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [API Documentation](#api-documentation)
- [Development Setup](#development-setup)
- [Production Deployment](#production-deployment)
- [Background Tasks](#background-tasks)
- [Monitoring and Logging](#monitoring-and-logging)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

## Features

### Core Features
- **Real-time ADR Quotes**
  - Live price updates from Polygon.io
  - Automatic currency conversion
  - Historical price data
  - Volume and market indicators

- **Exchange Rate Tracking**
  - Real-time USD/BRL rates
  - Historical exchange rates
  - Rate alerts and notifications
  - Central Bank integration

- **Portfolio Management**
  - Position tracking
  - Cost basis calculation
  - Performance metrics
  - Tax lot tracking
  - Dividend tracking
  - Capital gains calculation

- **Market Analysis**
  - S&P 500 vs Ibovespa correlation
  - Technical indicators
  - Market sentiment analysis
  - Volume analysis

- **Alerts System**
  - Price threshold alerts
  - Volume alerts
  - Technical indicator alerts
  - Custom alert conditions
  - Multiple notification channels

### Advanced Features
- **Tax Reporting**
  - Monthly tax position reports
  - Capital gains calculation
  - Dividend tax implications
  - IRPF (Brazilian tax return) support

- **Risk Analysis**
  - Portfolio diversification metrics
  - Currency exposure analysis
  - Correlation matrices
  - Value at Risk (VaR) calculations

- **API Rate Limiting**
  - Tiered access levels
  - Usage monitoring
  - Fair use policies
  - Burst handling

## Tech Stack

### Core Technologies
- **Framework**: Django 4.2.21
  - Django REST Framework for API
  - Django ORM for database operations
  - Django Channels for real-time updates

- **Database**: PostgreSQL
  - TimescaleDB extension for time-series data
  - Partitioned tables for performance
  - Full-text search capabilities

- **Cache Layer**: Redis
  - Session management
  - Rate limiting
  - Real-time data caching
  - Pub/Sub for notifications

- **Task Queue**: Celery
  - Distributed task processing
  - Scheduled jobs
  - Error handling and retries
  - Task monitoring

### External Services
- **Market Data**
  - Polygon.io for ADR data
  - Brazilian Central Bank API for exchange rates
  - Yahoo Finance for indices

- **Infrastructure**
  - Docker containers
  - Nginx reverse proxy
  - uWSGI application server
  - SSL/TLS encryption

## API Documentation

### Authentication

```http
POST /api/auth/token/
```
Obtain authentication token.

Request:
```json
{
    "username": "user@example.com",
    "password": "secure_password"
}
```

Response:
```json
{
    "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "expires_at": "2025-06-25T23:20:08Z"
}
```

### ADR Endpoints

#### Get ADR Quote

```http
GET /api/adr/quote/{ticker}/
```

Parameters:
- `ticker`: ADR symbol (e.g., 'VALE', 'PBR')
- `currency`: Response currency (default: 'USD')
- `include_details`: Include additional market data (default: false)

Response:
```json
{
    "ticker": "VALE",
    "price_usd": 15.75,
    "price_brl": 78.75,
    "exchange_rate": 5.00,
    "volume": 12345678,
    "change_percent": -1.25,
    "timestamp": "2025-05-25T14:30:00Z",
    "details": {
        "bid": 15.74,
        "ask": 15.76,
        "day_high": 16.00,
        "day_low": 15.50,
        "52_week_high": 20.00,
        "52_week_low": 12.00
    }
}
```

#### Get Historical Prices

```http
GET /api/adr/historical/{ticker}/
```

Parameters:
- `ticker`: ADR symbol
- `start_date`: Start date (YYYY-MM-DD)
- `end_date`: End date (YYYY-MM-DD)
- `interval`: Data interval ('1d', '1h', '15min')
- `currency`: Response currency

Response:
```json
{
    "ticker": "VALE",
    "interval": "1d",
    "currency": "USD",
    "data": [
        {
            "timestamp": "2025-05-25T00:00:00Z",
            "open": 15.50,
            "high": 16.00,
            "low": 15.25,
            "close": 15.75,
            "volume": 12345678
        }
    ]
}
```

### Portfolio Endpoints

#### Add Transaction

```http
POST /api/portfolio/transaction/
```

Request:
```json
{
    "ticker": "VALE",
    "type": "BUY",
    "quantity": 100,
    "price_usd": 15.75,
    "date": "2025-05-25",
    "exchange_rate": 5.00,
    "fees_usd": 1.50,
    "notes": "Initial position"
}
```

#### Get Portfolio Summary

```http
GET /api/portfolio/summary/
```

Parameters:
- `date`: Summary date (default: today)
- `currency`: Response currency
- `include_history`: Include historical performance

Response:
```json
{
    "total_value_usd": 50000.00,
    "total_value_brl": 250000.00,
    "total_return_pct": 15.75,
    "currency_exposure": {
        "USD": 80.5,
        "BRL": 19.5
    },
    "holdings": [
        {
            "ticker": "VALE",
            "quantity": 1000,
            "avg_price_usd": 15.00,
            "current_price_usd": 15.75,
            "market_value_usd": 15750.00,
            "market_value_brl": 78750.00,
            "weight": 31.5,
            "return_pct": 5.00
        }
    ],
    "performance": {
        "1d": 0.5,
        "1w": 1.2,
        "1m": 3.5,
        "ytd": 12.5
    }
}
```

### Market Analysis Endpoints

#### Get Market Correlation

```http
GET /api/analysis/correlation/
```

Parameters:
- `index1`: First index (e.g., 'SPX', 'IBOV')
- `index2`: Second index
- `period`: Analysis period ('7d', '30d', '90d')

Response:
```json
{
    "period": "30d",
    "correlation": 0.85,
    "strength": "strong",
    "data_points": 30,
    "index1": {
        "name": "S&P 500",
        "return": 1.25,
        "volatility": 0.8
    },
    "index2": {
        "name": "Ibovespa",
        "return": 1.15,
        "volatility": 1.2
    },
    "analysis": [
        "Strong positive correlation in the last 30 days",
        "Both markets showing similar volatility patterns",
        "Correlation strengthening compared to previous period"
    ]
}
```

## Development Setup

### Prerequisites
- Python 3.13+
- PostgreSQL 15+
- Redis 7.2+
- Node.js 20+ (for frontend development)

### Local Environment Setup

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
# Edit .env with your configuration:
# - Database credentials
# - API keys (Polygon.io, etc.)
# - Redis connection
# - Email settings
```

5. Initialize the database:
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata initial_data
```

6. Start development services:
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery Worker
celery -A financeapi_br2 worker -l info

# Terminal 3: Celery Beat
celery -A financeapi_br2 beat -l info

# Terminal 4: Django Development Server
python manage.py runserver
```

### Development Tools

- **Code Quality**:
  ```bash
  # Format code
  black .
  isort .
  
  # Run linters
  flake8
  mypy .
  
  # Run tests
  pytest
  ```

- **Database Management**:
  ```bash
  # Create new migration
  python manage.py makemigrations
  
  # Show SQL for migration
  python manage.py sqlmigrate app_name migration_name
  
  # Check migration status
  python manage.py showmigrations
  ```

- **API Documentation**:
  ```bash
  # Generate OpenAPI schema
  python manage.py generateschema > openapi-schema.yml
  
  # Run documentation server
  python manage.py spectacular --file schema.yml
  ```

## Production Deployment

### System Requirements

- 4+ CPU cores
- 8GB+ RAM
- 50GB+ SSD storage
- Ubuntu 22.04 LTS or similar

### Security Configuration

1. SSL/TLS Setup:
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d api.financeapi-br.com.br
```

2. Firewall Configuration:
```bash
# Allow only necessary ports
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
```

3. Database Security:
```bash
# Configure PostgreSQL access
sudo nano /etc/postgresql/15/main/pg_hba.conf

# Set up database backup
sudo -u postgres pg_dump financeapi > backup.sql
```

### Monitoring Setup

1. Prometheus Configuration:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'django'
    static_configs:
      - targets: ['localhost:8000']
```

2. Grafana Dashboards:
- API performance metrics
- Database query monitoring
- Cache hit rates
- Task queue status

### Deployment Process

1. Build and push Docker images:
```bash
docker build -t financeapi-br .
docker push registry.example.com/financeapi-br
```

2. Deploy with Docker Compose:
```yaml
version: '3.8'
services:
  web:
    image: financeapi-br
    environment:
      - DJANGO_SETTINGS_MODULE=financeapi_br2.settings.prod
    depends_on:
      - db
      - redis
  db:
    image: postgres:15
    volumes:
      - pgdata:/var/lib/postgresql/data
  redis:
    image: redis:7.2
    volumes:
      - redisdata:/data
```

## Contributing

### Development Workflow

1. Fork the repository
2. Create a feature branch:
```bash
git checkout -b feature/new-feature
```

3. Make your changes:
- Write tests for new functionality
- Follow code style guidelines
- Update documentation

4. Submit a pull request:
- Clear description of changes
- Link to related issues
- Test results and coverage

### Code Style

- Follow PEP 8 guidelines
- Use type hints
- Write docstrings for public APIs
- Keep functions focused and small

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- GitHub Issues: Technical problems and feature requests
- Email: support@financeapi-br.com.br
- Documentation: https://docs.financeapi-br.com.br

## Acknowledgments

- Polygon.io for market data
- Brazilian Central Bank for exchange rates
- Yahoo Finance for market indices
- All contributors and users of the API
