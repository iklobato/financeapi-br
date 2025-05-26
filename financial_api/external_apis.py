import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class PolygonAPI:
    """Integration with Polygon.io API for ADR data"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or settings.POLYGON_API_KEY
        if not self.api_key:
            raise ValueError("Polygon API key is required. Please set POLYGON_API_KEY in your environment variables.")
        self.base_url = "https://api.polygon.io"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}'
        })
    
    def _handle_response_error(self, response, ticker):
        """Handle API response errors"""
        try:
            error_data = response.json()
            error_message = error_data.get('message', 'Unknown error')
            if response.status_code == 403:
                logger.error(f"Authentication error with Polygon API: {error_message}")
                raise ValueError(f"Polygon API authentication failed: {error_message}")
            elif response.status_code == 429:
                logger.warning(f"Rate limit exceeded for Polygon API: {error_message}")
                raise ValueError(f"Polygon API rate limit exceeded: {error_message}")
            else:
                logger.error(f"Polygon API error ({response.status_code}): {error_message}")
                raise ValueError(f"Polygon API error: {error_message}")
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error parsing Polygon API response for {ticker}: {e}")
            raise ValueError(f"Error processing Polygon API response: {str(e)}")
    
    def get_last_trade(self, ticker):
        """Get the last trade for a ticker"""
        try:
            url = f"{self.base_url}/v2/last/trade/{ticker}"
            
            response = self.session.get(url, timeout=5)
            if response.status_code != 200:
                self._handle_response_error(response, ticker)
            
            data = response.json()
            
            if data.get('status') == 'OK' and 'results' in data:
                result = data['results']
                return {
                    'ticker': ticker,
                    'price': Decimal(str(result.get('p', 0))),
                    'volume': result.get('s', 0),
                    'timestamp': datetime.fromtimestamp(result.get('t', 0) / 1000),
                    'source': 'polygon'
                }
            
            logger.warning(f"No quote data found for {ticker}")
            return None
            
        except ValueError as e:
            logger.error(str(e))
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data from Polygon API for {ticker}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Polygon API for {ticker}: {e}")
            return None
    
    def get_historical_data(self, ticker, from_date, to_date):
        """Get historical OHLCV data for a ticker"""
        try:
            url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == 'OK' and 'results' in data:
                results = []
                for item in data['results']:
                    results.append({
                        'date': datetime.fromtimestamp(item['t'] / 1000).date(),
                        'open': Decimal(str(item['o'])),
                        'high': Decimal(str(item['h'])),
                        'low': Decimal(str(item['l'])),
                        'close': Decimal(str(item['c'])),
                        'volume': item['v']
                    })
                return results
            
            logger.warning(f"No historical data found for {ticker}")
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching historical data from Polygon API for {ticker}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in Polygon historical data for {ticker}: {e}")
            return []
    
    def get_news(self, ticker=None, limit=10):
        """Get news articles for a ticker or general market news"""
        try:
            url = f"{self.base_url}/v2/reference/news"
            params = {
                'limit': limit,
                'order': 'desc'
            }
            
            if ticker:
                params['ticker'] = ticker
            
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == 'OK' and 'results' in data:
                return data['results']
            
            logger.warning(f"No news data found for {ticker if ticker else 'market'}")
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching news from Polygon API: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in Polygon news API: {e}")
            return []


class BrazilianCentralBankAPI:
    """Integration with Brazilian Central Bank API for exchange rates and economic data"""
    
    def __init__(self):
        self.base_url = "https://api.bcb.gov.br/dados"
        self.session = requests.Session()
    
    def get_usd_brl_rate(self):
        """Get current USD/BRL exchange rate"""
        cache_key = 'usd_brl_rate_current'
        cached_rate = cache.get(cache_key)
        
        if cached_rate:
            return cached_rate
        
        try:
            # Series 1 is USD/BRL exchange rate
            url = f"{self.base_url}/serie/bcdata.sgs.1/dados/ultimos/1"
            params = {'formato': 'json'}
            
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data and len(data) > 0:
                rate_data = data[0]
                rate = Decimal(str(rate_data['valor']))
                
                # Cache for 5 minutes
                cache.set(cache_key, {
                    'rate': rate,
                    'date': rate_data['data'],
                    'source': 'bcb'
                }, 300)
                
                return {
                    'rate': rate,
                    'date': rate_data['data'],
                    'source': 'bcb'
                }
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching USD/BRL rate from BCB API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in BCB USD/BRL rate API: {e}")
            return None
    
    def get_selic_rate(self):
        """Get current Selic rate"""
        cache_key = 'selic_rate_current'
        cached_rate = cache.get(cache_key)
        
        if cached_rate:
            return cached_rate
        
        try:
            # Series 432 is Selic rate
            url = f"{self.base_url}/serie/bcdata.sgs.432/dados/ultimos/1"
            params = {'formato': 'json'}
            
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data and len(data) > 0:
                rate_data = data[0]
                rate = Decimal(str(rate_data['valor']))
                
                # Cache for 1 hour
                cache.set(cache_key, {
                    'rate': rate,
                    'date': rate_data['data'],
                    'source': 'bcb'
                }, 3600)
                
                return {
                    'rate': rate,
                    'date': rate_data['data'],
                    'source': 'bcb'
                }
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Selic rate from BCB API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in BCB Selic rate API: {e}")
            return None
    
    def get_historical_exchange_rate(self, date):
        """Get USD/BRL rate for a specific date"""
        cache_key = f'usd_brl_rate_{date}'
        cached_rate = cache.get(cache_key)
        
        if cached_rate:
            return cached_rate
        
        try:
            # Format date for BCB API (DD/MM/YYYY)
            if isinstance(date, datetime):
                date_str = date.strftime('%d/%m/%Y')
            else:
                date_str = date.strftime('%d/%m/%Y')
            
            url = f"{self.base_url}/serie/bcdata.sgs.1/dados"
            params = {
                'formato': 'json',
                'dataInicial': date_str,
                'dataFinal': date_str
            }
            
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data and len(data) > 0:
                rate_data = data[0]
                rate = Decimal(str(rate_data['valor']))
                
                result = {
                    'rate': rate,
                    'date': rate_data['data'],
                    'source': 'bcb'
                }
                
                # Cache historical rates for 24 hours
                cache.set(cache_key, result, 86400)
                
                return result
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching historical USD/BRL rate from BCB API for {date}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in BCB historical rate API for {date}: {e}")
            return None


class YahooFinanceAPI:
    """Integration with Yahoo Finance for market indices data"""
    
    def __init__(self):
        self.session = requests.Session()
    
    def get_ibovespa_data(self):
        """Get Ibovespa (^BVSP) current data"""
        cache_key = 'ibovespa_current_data'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            ticker = yf.Ticker("^BVSP")
            info = ticker.info
            hist = ticker.history(period="2d")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                previous_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                change = current_price - previous_price
                change_percent = (change / previous_price) * 100 if previous_price != 0 else 0
                
                result = {
                    'symbol': '^BVSP',
                    'name': 'Ibovespa',
                    'price': Decimal(str(current_price)),
                    'change': Decimal(str(change)),
                    'change_percent': Decimal(str(change_percent)),
                    'volume': int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns else 0,
                    'timestamp': datetime.now(),
                    'source': 'yahoo'
                }
                
                # Cache for 1 minute
                cache.set(cache_key, result, 60)
                
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Ibovespa data from Yahoo Finance: {e}")
            return None
    
    def get_sp500_data(self):
        """Get S&P 500 (^GSPC) current data"""
        cache_key = 'sp500_current_data'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            ticker = yf.Ticker("^GSPC")
            hist = ticker.history(period="2d")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                previous_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                change = current_price - previous_price
                change_percent = (change / previous_price) * 100 if previous_price != 0 else 0
                
                result = {
                    'symbol': '^GSPC',
                    'name': 'S&P 500',
                    'price': Decimal(str(current_price)),
                    'change': Decimal(str(change)),
                    'change_percent': Decimal(str(change_percent)),
                    'volume': int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns else 0,
                    'timestamp': datetime.now(),
                    'source': 'yahoo'
                }
                
                # Cache for 1 minute
                cache.set(cache_key, result, 60)
                
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching S&P 500 data from Yahoo Finance: {e}")
            return None
    
    def get_historical_data(self, symbol, period="30d"):
        """Get historical data for a symbol"""
        cache_key = f'yahoo_historical_{symbol}_{period}'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return cached_data
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            
            if not hist.empty:
                result = []
                for date, row in hist.iterrows():
                    result.append({
                        'date': date.date(),
                        'open': Decimal(str(row['Open'])),
                        'high': Decimal(str(row['High'])),
                        'low': Decimal(str(row['Low'])),
                        'close': Decimal(str(row['Close'])),
                        'volume': int(row['Volume']) if 'Volume' in row else 0
                    })
                
                # Cache for 5 minutes
                cache.set(cache_key, result, 300)
                
                return result
            
            return []
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol} from Yahoo Finance: {e}")
            return []
    
    def calculate_returns(self, historical_data):
        """Calculate daily returns from historical data"""
        if len(historical_data) < 2:
            return []
        
        returns = []
        for i in range(1, len(historical_data)):
            current_price = historical_data[i]['close']
            previous_price = historical_data[i-1]['close']
            
            if previous_price != 0:
                daily_return = ((current_price - previous_price) / previous_price) * 100
                returns.append({
                    'date': historical_data[i]['date'],
                    'return': daily_return
                })
        
        return returns


class APIManager:
    """Manager for all external API interactions"""
    
    def __init__(self):
        self.polygon = PolygonAPI()
        self.bcb = BrazilianCentralBankAPI()
        self.yahoo = YahooFinanceAPI()
    
    def get_adr_quote_with_brl(self, ticker):
        """Get ADR quote with USD and BRL prices"""
        try:
            # Get USD quote from Polygon
            quote_data = self.polygon.get_last_trade(ticker)
            
            if not quote_data:
                logger.warning(f"No quote data found for {ticker}")
                return None
            
            # Get USD/BRL exchange rate
            exchange_rate_data = self.bcb.get_usd_brl_rate()
            
            if not exchange_rate_data:
                logger.warning("No exchange rate data found")
                return None
            
            # Calculate BRL price
            price_brl = quote_data['price'] * exchange_rate_data['rate']
            
            # Get daily change from Yahoo Finance
            yf_data = self.yahoo.get_historical_data(ticker, period="2d")
            change_percent = Decimal('0.00')
            
            if yf_data and len(yf_data) >= 2:
                prev_close = yf_data[-2]['close']
                current_price = yf_data[-1]['close']
                change_percent = ((current_price - prev_close) / prev_close) * 100
            
            return {
                'ticker': ticker,
                'price_usd': quote_data['price'],
                'price_brl': price_brl,
                'exchange_rate': exchange_rate_data['rate'],
                'volume': quote_data['volume'],
                'change_percent_day': change_percent,
                'timestamp': quote_data['timestamp'],
                'source': quote_data['source'],
                'delay_minutes': 15  # Standard delay for free tier
            }
            
        except Exception as e:
            logger.error(f"Error in get_adr_quote_with_brl for {ticker}: {e}")
            return None
    
    def get_market_correlation_data(self):
        """Get correlation data between SP500 and Ibovespa"""
        try:
            # Get historical data for both indices
            sp500_data = self.yahoo.get_historical_data("^GSPC", "30d")
            ibovespa_data = self.yahoo.get_historical_data("^BVSP", "30d")
            
            if not sp500_data or not ibovespa_data:
                logger.warning("Insufficient data for correlation calculation")
                return None
            
            # Calculate returns
            sp500_returns = self.yahoo.calculate_returns(sp500_data)
            ibovespa_returns = self.yahoo.calculate_returns(ibovespa_data)
            
            # Align dates and calculate correlation
            return self._calculate_correlation(sp500_returns, ibovespa_returns)
            
        except Exception as e:
            logger.error(f"Error calculating market correlation: {e}")
            return None
    
    def _calculate_correlation(self, sp500_returns, ibovespa_returns):
        """Calculate correlation between two return series"""
        try:
            import numpy as np
            from scipy.stats import pearsonr
            
            # Create aligned datasets
            sp500_dict = {item['date']: item['return'] for item in sp500_returns}
            ibovespa_dict = {item['date']: item['return'] for item in ibovespa_returns}
            
            common_dates = set(sp500_dict.keys()) & set(ibovespa_dict.keys())
            
            if len(common_dates) < 7:
                logger.warning("Insufficient common dates for correlation calculation")
                return None
            
            sorted_dates = sorted(common_dates)
            
            sp500_values = [float(sp500_dict[date]) for date in sorted_dates]
            ibovespa_values = [float(ibovespa_dict[date]) for date in sorted_dates]
            
            # Calculate correlations
            correlation_30d, _ = pearsonr(sp500_values, ibovespa_values)
            
            # Calculate 7-day correlation
            if len(sorted_dates) >= 7:
                recent_dates = sorted_dates[-7:]
                sp500_7d = [float(sp500_dict[date]) for date in recent_dates]
                ibovespa_7d = [float(ibovespa_dict[date]) for date in recent_dates]
                correlation_7d, _ = pearsonr(sp500_7d, ibovespa_7d)
            else:
                correlation_7d = correlation_30d
            
            return {
                'correlation_30d': Decimal(str(correlation_30d)),
                'correlation_7d': Decimal(str(correlation_7d)),
                'sp500_return': Decimal(str(sp500_values[-1])) if sp500_values else Decimal('0'),
                'ibovespa_return': Decimal(str(ibovespa_values[-1])) if ibovespa_values else Decimal('0'),
                'date': sorted_dates[-1] if sorted_dates else datetime.now().date()
            }
            
        except Exception as e:
            logger.error(f"Error in correlation calculation: {e}")
            return None 