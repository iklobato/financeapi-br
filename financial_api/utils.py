from decimal import Decimal
from datetime import datetime, date, timedelta
from collections import defaultdict
import logging
from django.core.cache import cache
from django.utils import timezone
from .models import Transaction, Portfolio, ADRQuote, ExchangeRate
from .external_apis import APIManager
from django.core.mail import send_mail
from twilio.rest import Client
import statistics
import math
import time
import numpy

logger = logging.getLogger(__name__)


class TaxCalculator:
    """Brazilian tax calculator for ADR transactions with enhanced features"""
    
    TAX_RATE = Decimal('0.15')  # 15% tax on capital gains
    MONTHLY_EXEMPTION = Decimal('20000.00')  # R$ 20,000 monthly exemption
    DAY_TRADE_TAX_RATE = Decimal('0.20')  # 20% for day trade operations
    IRRF_RATE = Decimal('0.00005')  # 0.005% IRRF on sales
    SWING_TRADE_EXEMPTION = Decimal('20000.00')  # R$ 20,000 monthly exemption for swing trades
    DAY_TRADE_EXEMPTION = Decimal('0.00')  # No exemption for day trades
    LOSS_CARRYFORWARD_LIMIT = 0  # No limit for loss carryforward in Brazil
    
    # Corporate action types
    CORPORATE_ACTIONS = {
        'split': 'stock_split',
        'reverse_split': 'reverse_stock_split',
        'spinoff': 'spinoff',
        'merger': 'merger',
        'acquisition': 'acquisition'
    }
    
    def __init__(self, user, year):
        self.user = user
        self.year = year
        self.transactions = Transaction.objects.filter(
            user=user,
            date__year=year
        ).order_by('date', 'created_at')
        
        # Get previous year's compensable losses
        previous_year = self.get_previous_year_losses()
        self.compensable_losses = previous_year.get('compensable_losses', Decimal('0.00'))
        self.day_trade_compensable_losses = previous_year.get('day_trade_compensable_losses', Decimal('0.00'))
        
        # Track corporate actions
        self.corporate_actions = {}  # ticker -> list of actions
        
        # Initialize tax optimization opportunities
        self.tax_opportunities = []
    
    def handle_corporate_action(self, action_type, ticker, date, ratio=None, new_ticker=None):
        """Handle corporate actions like splits, mergers, etc."""
        if action_type not in self.CORPORATE_ACTIONS:
            raise ValueError(f"Unsupported corporate action: {action_type}")
        
        if ticker not in self.corporate_actions:
            self.corporate_actions[ticker] = []
        
        self.corporate_actions[ticker].append({
            'type': action_type,
            'date': date,
            'ratio': ratio,
            'new_ticker': new_ticker
        })
    
    def adjust_quantity_for_corporate_actions(self, ticker, quantity, date):
        """Adjust quantity based on corporate actions"""
        if ticker not in self.corporate_actions:
            return quantity
        
        adjusted_quantity = quantity
        
        for action in self.corporate_actions[ticker]:
            if action['date'] <= date:
                if action['type'] == 'stock_split':
                    adjusted_quantity *= action['ratio']
                elif action['type'] == 'reverse_stock_split':
                    adjusted_quantity /= action['ratio']
                elif action['type'] in ['spinoff', 'merger', 'acquisition']:
                    # Handle more complex corporate actions
                    pass
        
        return adjusted_quantity
    
    def calculate_tax_optimization_opportunities(self, yearly_summary):
        """Calculate tax optimization opportunities"""
        opportunities = []
        
        # Check for wash sale opportunities
        if yearly_summary['total_losses'] > 0:
            opportunities.append({
                'type': 'wash_sale_warning',
                'message': (
                    "Atenção para operações de wash sale que podem ser "
                    "questionadas pela Receita Federal. Mantenha um intervalo "
                    "adequado entre vendas com prejuízo e recompras."
                )
            })
        
        # Monthly exemption optimization
        monthly_sales = defaultdict(Decimal)
        for month_data in yearly_summary['monthly_breakdown']:
            month = month_data['month']
            monthly_sales[month] = month_data['sales_total']
        
        for month, sales in monthly_sales.items():
            if sales > self.MONTHLY_EXEMPTION * Decimal('0.9'):
                opportunities.append({
                    'type': 'exemption_limit',
                    'month': month,
                    'message': (
                        f"Vendas em {month} próximas ao limite de isenção. "
                        "Considere postergar vendas adicionais para o próximo mês."
                    )
                })
        
        # Loss harvesting opportunities
        if yearly_summary['total_gains'] > 0:
            opportunities.append({
                'type': 'loss_harvesting',
                'message': (
                    "Oportunidade de tax loss harvesting identificada. "
                    "Considere realizar perdas para compensar ganhos de "
                    f"R$ {yearly_summary['total_gains']:.2f}."
                )
            })
        
        # Day trade optimization
        if yearly_summary['day_trade_gains'] > 0:
            opportunities.append({
                'type': 'day_trade_conversion',
                'message': (
                    "Considere converter operações day trade em swing trade "
                    "para aproveitar a isenção mensal de R$ 20.000."
                )
            })
        
        return opportunities
    
    def generate_recommendations(self, yearly_summary):
        """Generate enhanced tax optimization recommendations"""
        recommendations = []
        
        # Calculate optimization opportunities
        opportunities = self.calculate_tax_optimization_opportunities(yearly_summary)
        
        # Add basic recommendations
        if yearly_summary['total_exempted_sales'] > self.MONTHLY_EXEMPTION * Decimal('0.8'):
            recommendations.append(
                "Você está próximo do limite de isenção mensal. "
                "Considere postergar vendas para o próximo mês."
            )
        
        # Add sophisticated recommendations based on opportunities
        for opportunity in opportunities:
            if opportunity['type'] == 'wash_sale_warning':
                recommendations.append(opportunity['message'])
            elif opportunity['type'] == 'exemption_limit':
                recommendations.append(opportunity['message'])
            elif opportunity['type'] == 'loss_harvesting':
                recommendations.append(opportunity['message'])
            elif opportunity['type'] == 'day_trade_conversion':
                recommendations.append(opportunity['message'])
        
        # Loss carryforward recommendations
        if yearly_summary['compensable_losses'] > 0:
            recommendations.append(
                f"Você tem R$ {yearly_summary['compensable_losses']:.2f} em prejuízos "
                "acumulados que podem ser compensados em ganhos futuros. "
                "Planeje suas operações para otimizar o uso destes prejuízos."
            )
        
        if yearly_summary['day_trade_compensable_losses'] > 0:
            recommendations.append(
                f"Você tem R$ {yearly_summary['day_trade_compensable_losses']:.2f} em "
                "prejuízos de day trade que podem ser compensados em operações futuras. "
                "Considere realizar day trades com potencial de lucro para aproveitar "
                "estes prejuízos."
            )
        
        # IRRF optimization
        if yearly_summary['irrf_paid'] > 0:
            recommendations.append(
                f"IRRF pago de R$ {yearly_summary['irrf_paid']:.2f} pode ser "
                "compensado do imposto devido no ajuste anual. Mantenha a documentação "
                "das operações para comprovar o recolhimento."
            )
        
        # Previous year losses usage
        if yearly_summary['previous_year_losses_used'] > 0:
            recommendations.append(
                f"Você compensou R$ {yearly_summary['previous_year_losses_used']:.2f} "
                "em prejuízos de anos anteriores. Continue monitorando oportunidades "
                "de compensação de perdas."
            )
        
        # Tax efficiency recommendations
        total_tax = yearly_summary['tax_owed'] + yearly_summary['day_trade_tax']
        total_profit = yearly_summary['total_gains'] + yearly_summary['day_trade_gains']
        
        if total_profit > 0:
            effective_tax_rate = (total_tax / total_profit) * 100
            recommendations.append(
                f"Sua alíquota efetiva de imposto é {effective_tax_rate:.1f}%. "
                "Considere estratégias para reduzir a carga tributária, como "
                "aproveitamento da isenção mensal e compensação de perdas."
            )
        
        if not recommendations:
            recommendations.append(
                "Sua estratégia fiscal está otimizada. Continue monitorando "
                "os limites de isenção e oportunidades de compensação de perdas."
            )
        
        return recommendations
    
    def get_previous_year_losses(self):
        """Get compensable losses from previous year"""
        try:
            previous_year = self.year - 1
            previous_calculator = TaxCalculator(self.user, previous_year)
            return previous_calculator.calculate_taxes()
        except Exception:
            return {}
    
    def calculate_taxes(self):
        """Calculate taxes for the year using FIFO method"""
        try:
            monthly_data = self.group_transactions_by_month()
            yearly_summary = {
                'year': self.year,
                'total_gains': Decimal('0.00'),
                'total_losses': Decimal('0.00'),
                'net_gains': Decimal('0.00'),
                'tax_owed': Decimal('0.00'),
                'irrf_paid': Decimal('0.00'),
                'day_trade_gains': Decimal('0.00'),
                'day_trade_losses': Decimal('0.00'),
                'day_trade_tax': Decimal('0.00'),
                'monthly_breakdown': [],
                'recommendations': [],
                'compensable_losses': Decimal('0.00'),  # For next year
                'day_trade_compensable_losses': Decimal('0.00'),  # For next year
                'previous_year_losses_used': Decimal('0.00'),
                'previous_year_day_trade_losses_used': Decimal('0.00'),
                'total_exempted_gains': Decimal('0.00'),
                'total_exempted_sales': Decimal('0.00')
            }
            
            # Track holdings across months using FIFO
            holdings = defaultdict(list)  # ticker -> list of (quantity, price, date)
            remaining_compensable_losses = self.compensable_losses
            remaining_day_trade_losses = self.day_trade_compensable_losses
            
            for month, transactions in monthly_data.items():
                month_result = self.calculate_month_taxes(
                    transactions,
                    holdings,
                    month,
                    remaining_compensable_losses,
                    remaining_day_trade_losses
                )
                
                yearly_summary['monthly_breakdown'].append(month_result)
                yearly_summary['total_gains'] += month_result['gains']
                yearly_summary['total_losses'] += month_result['losses']
                yearly_summary['day_trade_gains'] += month_result['day_trade_gains']
                yearly_summary['day_trade_losses'] += month_result['day_trade_losses']
                yearly_summary['irrf_paid'] += month_result['irrf_paid']
                yearly_summary['total_exempted_gains'] += month_result['exempted_gains']
                yearly_summary['total_exempted_sales'] += month_result['exempted_sales']
                
                # Update remaining compensable losses
                remaining_compensable_losses = month_result['remaining_compensable_losses']
                remaining_day_trade_losses = month_result['remaining_day_trade_losses']
                
                yearly_summary['previous_year_losses_used'] += (
                    month_result['compensable_losses_used']
                )
                yearly_summary['previous_year_day_trade_losses_used'] += (
                    month_result['day_trade_losses_used']
                )
            
            # Calculate net gains separately for day trade and normal operations
            normal_net_gains = yearly_summary['total_gains'] - yearly_summary['total_losses']
            day_trade_net_gains = yearly_summary['day_trade_gains'] - yearly_summary['day_trade_losses']
            
            # Calculate taxes
            if normal_net_gains > 0:
                yearly_summary['tax_owed'] += normal_net_gains * self.TAX_RATE
            
            if day_trade_net_gains > 0:
                yearly_summary['day_trade_tax'] = day_trade_net_gains * self.DAY_TRADE_TAX_RATE
            
            # Total tax owed is the sum of both types minus IRRF paid
            total_tax = yearly_summary['tax_owed'] + yearly_summary['day_trade_tax']
            yearly_summary['tax_owed'] = max(total_tax - yearly_summary['irrf_paid'], Decimal('0.00'))
            
            # Calculate compensable losses for next year
            if normal_net_gains < 0:
                yearly_summary['compensable_losses'] = abs(normal_net_gains)
            
            if day_trade_net_gains < 0:
                yearly_summary['day_trade_compensable_losses'] = abs(day_trade_net_gains)
            
            # Generate recommendations
            yearly_summary['recommendations'] = self.generate_recommendations(
                yearly_summary
            )
            
            return yearly_summary
            
        except Exception as e:
            logger.error(f"Error calculating taxes for user {self.user.id}: {e}")
            raise
    
    def group_transactions_by_month(self):
        """Group transactions by month"""
        monthly_data = defaultdict(list)
        
        for transaction in self.transactions:
            month_key = f"{transaction.date.year}-{transaction.date.month:02d}"
            monthly_data[month_key].append(transaction)
        
        return monthly_data
    
    def calculate_month_taxes(self, transactions, holdings, month, compensable_losses, day_trade_losses):
        """Calculate taxes for a specific month"""
        month_gains = Decimal('0.00')
        month_losses = Decimal('0.00')
        month_sales_total = Decimal('0.00')
        day_trade_gains = Decimal('0.00')
        day_trade_losses = Decimal('0.00')
        irrf_paid = Decimal('0.00')
        exempted_gains = Decimal('0.00')
        exempted_sales = Decimal('0.00')
        compensable_losses_used = Decimal('0.00')
        day_trade_losses_used = Decimal('0.00')
        
        # Group transactions by date to identify day trades
        daily_transactions = defaultdict(list)
        for transaction in transactions:
            daily_transactions[transaction.date].append(transaction)
        
        for date, day_transactions in daily_transactions.items():
            # Process day trades first
            day_trade_results = self.process_day_trades(day_transactions)
            
            # Apply day trade losses from previous year first
            if day_trade_results['gains'] > 0 and day_trade_losses > 0:
                losses_to_use = min(day_trade_results['gains'], day_trade_losses)
                day_trade_results['gains'] -= losses_to_use
                day_trade_losses -= losses_to_use
                day_trade_losses_used += losses_to_use
            
            day_trade_gains += day_trade_results['gains']
            day_trade_losses += day_trade_results['losses']
            
            # Process remaining normal transactions
            for transaction in day_transactions:
                if transaction.transaction_type == 'sell':
                    # Calculate IRRF
                    irrf = transaction.total_value_brl * self.IRRF_RATE
                    irrf_paid += irrf
                    month_sales_total += transaction.total_value_brl
                    
                    if not transaction.is_day_trade:  # Skip if already processed as day trade
                        # Calculate gain/loss using FIFO
                        gain_loss = self.calculate_fifo_gain_loss(
                            transaction, holdings[transaction.ticker]
                        )
                        
                        if gain_loss > 0:
                            # Apply compensable losses from previous year first
                            if compensable_losses > 0:
                                losses_to_use = min(gain_loss, compensable_losses)
                                gain_loss -= losses_to_use
                                compensable_losses -= losses_to_use
                                compensable_losses_used += losses_to_use
                            
                            month_gains += gain_loss
                        else:
                            month_losses += abs(gain_loss)
                
                elif transaction.transaction_type == 'buy' and not transaction.is_day_trade:
                    # Add to holdings
                    holdings[transaction.ticker].append({
                        'quantity': transaction.quantity,
                        'price': transaction.price_usd,
                        'exchange_rate': transaction.exchange_rate,
                        'date': transaction.date,
                        'brokerage_fee': transaction.brokerage_fee
                    })
        
        # Apply monthly exemption for swing trades
        net_gains = month_gains - month_losses
        if net_gains > 0 and month_sales_total <= self.SWING_TRADE_EXEMPTION:
            exempted_gains = net_gains
            exempted_sales = month_sales_total
            taxable_gains = Decimal('0.00')
        else:
            taxable_gains = net_gains if net_gains > 0 else Decimal('0.00')
        
        return {
            'month': month,
            'gains': month_gains,
            'losses': month_losses,
            'net_gains': net_gains,
            'sales_total': month_sales_total,
            'taxable_gains': taxable_gains,
            'day_trade_gains': day_trade_gains,
            'day_trade_losses': day_trade_losses,
            'irrf_paid': irrf_paid,
            'exempt': month_sales_total <= self.MONTHLY_EXEMPTION,
            'exempted_gains': exempted_gains,
            'exempted_sales': exempted_sales,
            'remaining_compensable_losses': compensable_losses,
            'remaining_day_trade_losses': day_trade_losses,
            'compensable_losses_used': compensable_losses_used,
            'day_trade_losses_used': day_trade_losses_used
        }
    
    def process_day_trades(self, transactions):
        """Process day trade operations"""
        result = {'gains': Decimal('0.00'), 'losses': Decimal('0.00')}
        
        # Group by ticker
        ticker_transactions = defaultdict(list)
        for t in transactions:
            ticker_transactions[t.ticker].append(t)
        
        for ticker, ticker_txs in ticker_transactions.items():
            buys = [t for t in ticker_txs if t.transaction_type == 'buy']
            sells = [t for t in ticker_txs if t.transaction_type == 'sell']
            
            # Match buys and sells for day trades
            for buy in buys:
                for sell in sells:
                    if buy.quantity > 0 and sell.quantity > 0:
                        # Calculate day trade quantity
                        day_trade_qty = min(buy.quantity, sell.quantity)
                        
                        # Calculate gain/loss
                        buy_value = day_trade_qty * buy.price_usd * buy.exchange_rate
                        sell_value = day_trade_qty * sell.price_usd * sell.exchange_rate
                        gain_loss = sell_value - buy_value
                        
                        # Update quantities
                        buy.quantity -= day_trade_qty
                        sell.quantity -= day_trade_qty
                        
                        # Mark as day trade
                        buy.is_day_trade = True
                        sell.is_day_trade = True
                        
                        if gain_loss > 0:
                            result['gains'] += gain_loss
                        else:
                            result['losses'] += abs(gain_loss)
        
        return result
    
    def calculate_fifo_gain_loss(self, sell_transaction, holdings):
        """Calculate gain/loss using FIFO method"""
        remaining_quantity = sell_transaction.quantity
        total_gain_loss = Decimal('0.00')
        
        while remaining_quantity > 0 and holdings:
            holding = holdings[0]
            
            if holding['quantity'] <= remaining_quantity:
                # Use entire holding
                quantity_used = holding['quantity']
                remaining_quantity -= quantity_used
                holdings.pop(0)
            else:
                # Use partial holding
                quantity_used = remaining_quantity
                holding['quantity'] -= quantity_used
                remaining_quantity = Decimal('0.00')
            
            # Calculate gain/loss for this portion
            cost_basis_usd = quantity_used * holding['price']
            cost_basis_brl = cost_basis_usd * holding['exchange_rate']
            
            sale_value_usd = quantity_used * sell_transaction.price_usd
            sale_value_brl = sale_value_usd * sell_transaction.exchange_rate
            
            gain_loss = sale_value_brl - cost_basis_brl
            total_gain_loss += gain_loss
        
        return total_gain_loss


class PortfolioAnalyzer:
    """Portfolio analysis with advanced metrics and ML-based recommendations"""
    
    # Risk-free rate thresholds
    LOW_RISK_FREE = Decimal('0.02')  # 2%
    HIGH_RISK_FREE = Decimal('0.08')  # 8%
    
    # Portfolio concentration thresholds
    MAX_POSITION_WEIGHT = Decimal('0.30')  # 30% max in single position
    MAX_SECTOR_WEIGHT = Decimal('0.40')  # 40% max in single sector
    
    # Risk metrics thresholds
    HIGH_VOLATILITY = Decimal('0.25')  # 25% annualized volatility
    HIGH_BETA = Decimal('1.30')  # 30% more volatile than market
    LOW_BETA = Decimal('0.70')  # 30% less volatile than market
    
    # Diversification scores
    POOR_DIVERSIFICATION = Decimal('40.00')
    GOOD_DIVERSIFICATION = Decimal('70.00')
    
    def __init__(self, user):
        self.user = user
        self.portfolio = Portfolio.objects.filter(user=user).select_related('user')
        self.api_manager = APIManager()
        self.risk_free_rate = self.api_manager.get_selic_rate()
        self.market_data = self._get_market_data()
    
    def _get_market_data(self):
        """Get market data for analysis"""
        try:
            return {
                'ibovespa': self.api_manager.get_historical_data('^BVSP'),
                'sp500': self.api_manager.get_historical_data('^GSPC'),
                'volatility_index': self.api_manager.get_historical_data('^VIX'),
                'exchange_rate': self.api_manager.get_current_exchange_rate(),
                'sector_performance': self.api_manager.get_sector_performance()
            }
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return {}
    
    def analyze_portfolio(self):
        """Analyze portfolio with advanced metrics and ML-based insights"""
        try:
            holdings = self.get_current_holdings()
            if not holdings:
                return {'error': 'No holdings found in portfolio'}
            
            # Get current market data
            tickers = [h['ticker'] for h in holdings]
            quotes = self.api_manager.get_adr_quotes(tickers)
            
            # Calculate basic portfolio metrics
            portfolio_metrics = self._calculate_basic_metrics(holdings, quotes)
            
            # Calculate advanced risk metrics
            risk_metrics = self._calculate_risk_metrics(holdings, portfolio_metrics)
            
            # Calculate factor exposures
            factor_exposures = self._calculate_factor_exposures(holdings)
            
            # Generate ML-based recommendations
            recommendations = self._generate_ml_recommendations(
                portfolio_metrics,
                risk_metrics,
                factor_exposures
            )
            
            return {
                **portfolio_metrics,
                'risk_metrics': risk_metrics,
                'factor_exposures': factor_exposures,
                'recommendations': recommendations
            }
            
        except Exception as e:
            logger.error(f"Error analyzing portfolio for user {self.user.id}: {e}")
            raise
    
    def _calculate_basic_metrics(self, holdings, quotes):
        """Calculate basic portfolio metrics"""
        total_value_usd = Decimal('0.00')
        total_value_brl = Decimal('0.00')
        total_cost_basis_usd = Decimal('0.00')
        total_cost_basis_brl = Decimal('0.00')
        holdings_analysis = []
        
        for holding in holdings:
            ticker = holding['ticker']
            if ticker not in quotes:
                continue
            
            current_price_usd = Decimal(str(quotes[ticker]))
            quantity = holding['quantity']
            
            # Calculate holding metrics
            current_value_usd = current_price_usd * quantity
            current_value_brl = current_value_usd * self.market_data['exchange_rate']
            cost_basis_usd = holding['average_cost_usd'] * quantity
            cost_basis_brl = holding['average_cost_brl']
            
            holding_analysis = {
                'ticker': ticker,
                'quantity': quantity,
                'current_price_usd': current_price_usd,
                'current_price_brl': current_price_usd * self.market_data['exchange_rate'],
                'average_cost_usd': holding['average_cost_usd'],
                'average_cost_brl': holding['average_cost_brl'] / quantity,
                'current_value_usd': current_value_usd,
                'current_value_brl': current_value_brl,
                'cost_basis_usd': cost_basis_usd,
                'cost_basis_brl': cost_basis_brl,
                'unrealized_gain_usd': current_value_usd - cost_basis_usd,
                'unrealized_gain_brl': current_value_brl - cost_basis_brl,
                'total_return_pct': (
                    ((current_value_brl / cost_basis_brl) - 1) * 100
                    if cost_basis_brl > 0 else Decimal('0.00')
                ),
                'weight': Decimal('0.00')  # Will be calculated after total is known
            }
            
            holdings_analysis.append(holding_analysis)
            total_value_usd += current_value_usd
            total_value_brl += current_value_brl
            total_cost_basis_usd += cost_basis_usd
            total_cost_basis_brl += cost_basis_brl
        
        # Calculate weights
        for holding in holdings_analysis:
            holding['weight'] = (
                (holding['current_value_brl'] / total_value_brl)
                if total_value_brl > 0 else Decimal('0.00')
            )
        
        return {
            'total_value_usd': total_value_usd,
            'total_value_brl': total_value_brl,
            'total_cost_basis_usd': total_cost_basis_usd,
            'total_cost_basis_brl': total_cost_basis_brl,
            'holdings': holdings_analysis,
            'total_return_pct': (
                ((total_value_brl / total_cost_basis_brl) - 1) * 100
                if total_cost_basis_brl > 0 else Decimal('0.00')
            )
        }
    
    def _calculate_risk_metrics(self, holdings, portfolio_metrics):
        """Calculate advanced risk metrics"""
        try:
            # Calculate portfolio-level metrics
            holdings_data = portfolio_metrics['holdings']
            weights = [h['weight'] for h in holdings_data]
            
            # Get historical data for all holdings
            historical_data = {}
            for holding in holdings_data:
                ticker = holding['ticker']
                data = self.get_historical_metrics(ticker)
                historical_data[ticker] = data
            
            # Calculate portfolio volatility using correlation matrix
            correlation_matrix = self._calculate_correlation_matrix(historical_data)
            portfolio_volatility = self._calculate_portfolio_volatility(
                weights, 
                [data['volatility'] for data in historical_data.values()],
                correlation_matrix
            )
            
            # Calculate other risk metrics
            portfolio_beta = sum(
                w * data['beta'] 
                for w, data in zip(weights, historical_data.values())
            )
            
            var_95 = self._calculate_portfolio_var(
                weights,
                [data['var_95'] for data in historical_data.values()],
                correlation_matrix
            )
            
            # Calculate advanced risk metrics
            risk_metrics = {
                'portfolio_volatility': portfolio_volatility,
                'portfolio_beta': portfolio_beta,
                'value_at_risk_95': var_95,
                'expected_shortfall': self._calculate_expected_shortfall(
                    weights,
                    historical_data
                ),
                'tracking_error': self._calculate_tracking_error(
                    weights,
                    historical_data
                ),
                'information_ratio': self.calculate_information_ratio(holdings_data),
                'sortino_ratio': self._calculate_sortino_ratio(
                    portfolio_metrics['total_return_pct'],
                    weights,
                    historical_data
                ),
                'diversification_score': self.calculate_diversification_score(
                    holdings_data
                ),
                'currency_exposure': self.calculate_currency_exposure(
                    portfolio_metrics['total_value_brl'],
                    self.market_data['exchange_rate']
                ),
                'sector_exposure': self.calculate_sector_exposure(holdings_data),
                'risk_concentration': self.calculate_risk_concentration(holdings_data)
            }
            
            return risk_metrics
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {e}")
            return self.get_default_metrics()
    
    def _calculate_correlation_matrix(self, historical_data):
        """Calculate correlation matrix for portfolio holdings"""
        tickers = list(historical_data.keys())
        n = len(tickers)
        matrix = [[Decimal('1.00')] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                correlation = self.calculate_correlation(
                    historical_data[tickers[i]]['returns'],
                    historical_data[tickers[j]]['returns']
                )
                matrix[i][j] = correlation
                matrix[j][i] = correlation
        
        return matrix
    
    def _calculate_portfolio_volatility(self, weights, volatilities, correlation_matrix):
        """Calculate portfolio volatility using correlation matrix"""
        n = len(weights)
        portfolio_var = Decimal('0.00')
        
        for i in range(n):
            for j in range(n):
                portfolio_var += (
                    weights[i] * weights[j] *
                    volatilities[i] * volatilities[j] *
                    correlation_matrix[i][j]
                )
        
        return Decimal(str(math.sqrt(float(portfolio_var))))
    
    def _calculate_portfolio_var(self, weights, vars_95, correlation_matrix):
        """Calculate portfolio Value at Risk"""
        # Using historical simulation approach
        portfolio_var = sum(w * var for w, var in zip(weights, vars_95))
        return portfolio_var
    
    def _calculate_expected_shortfall(self, weights, historical_data):
        """Calculate Expected Shortfall (CVaR)"""
        try:
            # Get portfolio returns
            portfolio_returns = []
            for ticker, data in historical_data.items():
                weight = next(
                    (w for h in self.portfolio if h.ticker == ticker),
                    Decimal('0.00')
                )
                returns = data.get('returns', [])
                portfolio_returns.extend([r * weight for r in returns])
            
            # Sort returns and calculate ES
            if portfolio_returns:
                portfolio_returns.sort()
                cutoff = int(len(portfolio_returns) * 0.05)  # 95% confidence
                worst_returns = portfolio_returns[:cutoff]
                return Decimal(str(statistics.mean(worst_returns)))
            
            return Decimal('0.00')
            
        except Exception as e:
            logger.error(f"Error calculating Expected Shortfall: {e}")
            return Decimal('0.00')
    
    def _calculate_tracking_error(self, weights, historical_data):
        """Calculate tracking error against benchmark"""
        try:
            # Get benchmark returns (Ibovespa)
            benchmark_returns = self.market_data.get('ibovespa', [])
            if not benchmark_returns:
                return Decimal('0.00')
            
            # Calculate portfolio returns
            portfolio_returns = []
            for ticker, data in historical_data.items():
                weight = next(
                    (w for h in self.portfolio if h.ticker == ticker),
                    Decimal('0.00')
                )
                returns = data.get('returns', [])
                portfolio_returns.extend([r * weight for r in returns])
            
            # Calculate tracking error
            if portfolio_returns and len(portfolio_returns) == len(benchmark_returns):
                differences = [
                    p - b for p, b in zip(portfolio_returns, benchmark_returns)
                ]
                tracking_error = statistics.stdev(differences) * math.sqrt(252)
                return Decimal(str(tracking_error))
            
            return Decimal('0.00')
            
        except Exception as e:
            logger.error(f"Error calculating Tracking Error: {e}")
            return Decimal('0.00')
    
    def _calculate_sortino_ratio(self, return_pct, weights, historical_data):
        """Calculate Sortino ratio using downside deviation"""
        try:
            # Get portfolio returns
            portfolio_returns = []
            for ticker, data in historical_data.items():
                weight = next(
                    (w for h in self.portfolio if h.ticker == ticker),
                    Decimal('0.00')
                )
                returns = data.get('returns', [])
                portfolio_returns.extend([r * weight for r in returns])
            
            if not portfolio_returns:
                return Decimal('0.00')
            
            # Calculate downside deviation
            negative_returns = [r for r in portfolio_returns if r < 0]
            if negative_returns:
                downside_dev = statistics.stdev(negative_returns) * math.sqrt(252)
                if downside_dev > 0:
                    excess_return = return_pct - self.risk_free_rate
                    return excess_return / Decimal(str(downside_dev))
            
            return Decimal('0.00')
            
        except Exception as e:
            logger.error(f"Error calculating Sortino Ratio: {e}")
            return Decimal('0.00')
    
    def _calculate_factor_exposures(self, holdings):
        """Calculate factor exposures"""
        try:
            exposures = {
                'market_beta': self._calculate_market_exposure(holdings),
                'size': self._calculate_size_exposure(holdings),
                'value': self._calculate_value_exposure(holdings),
                'momentum': self._calculate_momentum_exposure(holdings),
                'quality': self._calculate_quality_exposure(holdings)
            }
            
            return exposures
            
        except Exception as e:
            logger.error(f"Error calculating factor exposures: {e}")
            return {}
    
    def _calculate_market_exposure(self, holdings):
        """Calculate market factor exposure"""
        try:
            portfolio_beta = Decimal('0.00')
            for holding in holdings:
                metrics = self.get_historical_metrics(holding['ticker'])
                portfolio_beta += holding['weight'] * metrics['beta']
            return portfolio_beta
        except Exception:
            return Decimal('1.00')
    
    def _calculate_size_exposure(self, holdings):
        """Calculate size factor exposure"""
        try:
            # Simplified size score based on market cap
            size_scores = []
            for holding in holdings:
                market_cap = self.api_manager.get_market_cap(holding['ticker'])
                if market_cap:
                    size_scores.append(holding['weight'] * Decimal(str(math.log(float(market_cap)))))
            return sum(size_scores) if size_scores else Decimal('0.00')
        except Exception:
            return Decimal('0.00')
    
    def _calculate_value_exposure(self, holdings):
        """Calculate value factor exposure"""
        try:
            # Use P/B ratio as value metric
            value_scores = []
            for holding in holdings:
                pb_ratio = self.api_manager.get_pb_ratio(holding['ticker'])
                if pb_ratio and pb_ratio > 0:
                    value_scores.append(holding['weight'] * (Decimal('1.00') / pb_ratio))
            return sum(value_scores) if value_scores else Decimal('0.00')
        except Exception:
            return Decimal('0.00')
    
    def _calculate_momentum_exposure(self, holdings):
        """Calculate momentum factor exposure"""
        try:
            momentum_scores = []
            for holding in holdings:
                returns_12m = self.api_manager.get_returns_12m(holding['ticker'])
                if returns_12m:
                    momentum_scores.append(holding['weight'] * returns_12m)
            return sum(momentum_scores) if momentum_scores else Decimal('0.00')
        except Exception:
            return Decimal('0.00')
    
    def _calculate_quality_exposure(self, holdings):
        """Calculate quality factor exposure"""
        try:
            quality_scores = []
            for holding in holdings:
                roe = self.api_manager.get_roe(holding['ticker'])
                if roe:
                    quality_scores.append(holding['weight'] * roe)
            return sum(quality_scores) if quality_scores else Decimal('0.00')
        except Exception:
            return Decimal('0.00')
    
    def _generate_ml_recommendations(self, portfolio_metrics, risk_metrics, factor_exposures):
        """Generate ML-based portfolio recommendations"""
        recommendations = []
        
        # Risk-based recommendations
        if risk_metrics['portfolio_volatility'] > self.HIGH_VOLATILITY:
            recommendations.append({
                'type': 'risk_warning',
                'message': (
                    "Volatilidade do portfólio está elevada. Considere: \n"
                    "1. Aumentar exposição a ativos defensivos\n"
                    "2. Implementar estratégias de hedge\n"
                    "3. Rebalancear para setores menos voláteis"
                ),
                'priority': 'high'
            })
        
        # Factor exposure recommendations
        market_beta = factor_exposures.get('market_beta', Decimal('1.00'))
        if market_beta > self.HIGH_BETA:
            recommendations.append({
                'type': 'factor_exposure',
                'message': (
                    "Alta exposição ao mercado (Beta > 1.3). Considere: \n"
                    "1. Aumentar posições em ativos defensivos\n"
                    "2. Adicionar proteções via opções\n"
                    "3. Diversificar com ativos não-correlacionados"
                ),
                'priority': 'medium'
            })
        
        # Diversification recommendations
        div_score = risk_metrics['diversification_score']
        if div_score < self.POOR_DIVERSIFICATION:
            recommendations.append({
                'type': 'diversification',
                'message': (
                    "Diversificação insuficiente. Sugestões: \n"
                    "1. Adicionar exposição a novos setores\n"
                    "2. Reduzir concentração em posições principais\n"
                    "3. Considerar ETFs para ampliar diversificação"
                ),
                'priority': 'high'
            })
        
        # Currency exposure recommendations
        curr_exposure = risk_metrics['currency_exposure']
        if curr_exposure['usd_exposure_pct'] > Decimal('70.00'):
            recommendations.append({
                'type': 'currency',
                'message': curr_exposure['hedge_suggestion'],
                'priority': 'medium'
            })
        
        # Performance optimization
        if portfolio_metrics['total_return_pct'] < 0:
            recommendations.append({
                'type': 'performance',
                'message': (
                    "Performance abaixo do esperado. Considere: \n"
                    "1. Revisar tese de investimento dos ativos\n"
                    "2. Avaliar stop loss em posições perdedoras\n"
                    "3. Aumentar exposição a setores com momentum positivo"
                ),
                'priority': 'high'
            })
        
        # Sort recommendations by priority
        recommendations.sort(
            key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[x['priority']]
        )
        
        return recommendations
    
    def get_current_holdings(self):
        """Get current holdings from transactions using FIFO"""
        try:
            transactions = Transaction.objects.filter(
                user=self.user
            ).order_by('date', 'id')
            
            holdings = {}
            
            for transaction in transactions:
                ticker = transaction.ticker
                
                if transaction.type == 'BUY':
                    if ticker not in holdings:
                        holdings[ticker] = {
                            'quantity': Decimal('0.00'),
                            'total_cost_usd': Decimal('0.00'),
                            'total_cost_brl': Decimal('0.00'),
                            'fifo_lots': []
                        }
                    
                    # Add new lot
                    holdings[ticker]['fifo_lots'].append({
                        'quantity': transaction.quantity,
                        'price_usd': transaction.price_usd,
                        'price_brl': transaction.price_brl,
                        'date': transaction.date
                    })
                    
                    holdings[ticker]['quantity'] += transaction.quantity
                    holdings[ticker]['total_cost_usd'] += (
                        transaction.quantity * transaction.price_usd
                    )
                    holdings[ticker]['total_cost_brl'] += (
                        transaction.quantity * transaction.price_brl
                    )
                
                elif transaction.type == 'SELL':
                    if ticker not in holdings:
                        logger.error(
                            f"Attempted to sell {ticker} but no holdings found"
                        )
                        continue
                    
                    remaining_quantity = transaction.quantity
                    realized_gain_usd = Decimal('0.00')
                    realized_gain_brl = Decimal('0.00')
                    
                    # Process FIFO lots
                    while (
                        remaining_quantity > 0 and
                        holdings[ticker]['fifo_lots']
                    ):
                        lot = holdings[ticker]['fifo_lots'][0]
                        
                        if lot['quantity'] <= remaining_quantity:
                            # Full lot sold
                            remaining_quantity -= lot['quantity']
                            holdings[ticker]['quantity'] -= lot['quantity']
                            holdings[ticker]['total_cost_usd'] -= (
                                lot['quantity'] * lot['price_usd']
                            )
                            holdings[ticker]['total_cost_brl'] -= (
                                lot['quantity'] * lot['price_brl']
                            )
                            
                            realized_gain_usd += (
                                lot['quantity'] * (
                                    transaction.price_usd - lot['price_usd']
                                )
                            )
                            realized_gain_brl += (
                                lot['quantity'] * (
                                    transaction.price_brl - lot['price_brl']
                                )
                            )
                            
                            holdings[ticker]['fifo_lots'].pop(0)
                        else:
                            # Partial lot sold
                            lot['quantity'] -= remaining_quantity
                            holdings[ticker]['quantity'] -= remaining_quantity
                            holdings[ticker]['total_cost_usd'] -= (
                                remaining_quantity * lot['price_usd']
                            )
                            holdings[ticker]['total_cost_brl'] -= (
                                remaining_quantity * lot['price_brl']
                            )
                            
                            realized_gain_usd += (
                                remaining_quantity * (
                                    transaction.price_usd - lot['price_usd']
                                )
                            )
                            realized_gain_brl += (
                                remaining_quantity * (
                                    transaction.price_brl - lot['price_brl']
                                )
                            )
                            
                            remaining_quantity = Decimal('0.00')
                    
                    # Record realized gains
                    if realized_gain_usd != 0 or realized_gain_brl != 0:
                        RealizedGain.objects.create(
                            user=self.user,
                            ticker=ticker,
                            amount_usd=realized_gain_usd,
                            amount_brl=realized_gain_brl,
                            transaction=transaction
                        )
                
                elif transaction.type == 'SPLIT':
                    if ticker in holdings:
                        split_ratio = transaction.split_ratio
                        
                        # Adjust quantities and costs
                        holdings[ticker]['quantity'] *= split_ratio
                        holdings[ticker]['total_cost_usd'] = (
                            holdings[ticker]['total_cost_usd']
                        )
                        holdings[ticker]['total_cost_brl'] = (
                            holdings[ticker]['total_cost_brl']
                        )
                        
                        # Adjust FIFO lots
                        for lot in holdings[ticker]['fifo_lots']:
                            lot['quantity'] *= split_ratio
                            lot['price_usd'] /= split_ratio
                            lot['price_brl'] /= split_ratio
                
                elif transaction.type == 'SPINOFF':
                    if ticker in holdings:
                        spinoff_ratio = transaction.spinoff_ratio
                        new_ticker = transaction.spinoff_ticker
                        
                        # Create new holding for spinoff
                        if new_ticker not in holdings:
                            holdings[new_ticker] = {
                                'quantity': Decimal('0.00'),
                                'total_cost_usd': Decimal('0.00'),
                                'total_cost_brl': Decimal('0.00'),
                                'fifo_lots': []
                            }
                        
                        # Transfer proportional holdings
                        spinoff_quantity = holdings[ticker]['quantity'] * spinoff_ratio
                        cost_ratio = transaction.spinoff_value_ratio
                        
                        # Adjust original holding
                        holdings[ticker]['quantity'] *= (1 - spinoff_ratio)
                        holdings[ticker]['total_cost_usd'] *= (1 - cost_ratio)
                        holdings[ticker]['total_cost_brl'] *= (1 - cost_ratio)
                        
                        # Add spinoff holding
                        holdings[new_ticker]['quantity'] += spinoff_quantity
                        holdings[new_ticker]['total_cost_usd'] += (
                            holdings[ticker]['total_cost_usd'] * cost_ratio
                        )
                        holdings[new_ticker]['total_cost_brl'] += (
                            holdings[ticker]['total_cost_brl'] * cost_ratio
                        )
                        
                        # Adjust FIFO lots
                        for lot in holdings[ticker]['fifo_lots']:
                            spinoff_lot = {
                                'quantity': lot['quantity'] * spinoff_ratio,
                                'price_usd': lot['price_usd'] * cost_ratio,
                                'price_brl': lot['price_brl'] * cost_ratio,
                                'date': transaction.date
                            }
                            holdings[new_ticker]['fifo_lots'].append(spinoff_lot)
                            
                            lot['quantity'] *= (1 - spinoff_ratio)
                            lot['price_usd'] *= (1 - cost_ratio)
                            lot['price_brl'] *= (1 - cost_ratio)
            
            # Convert holdings to list format
            holdings_list = []
            for ticker, data in holdings.items():
                if data['quantity'] > 0:
                    holdings_list.append({
                        'ticker': ticker,
                        'quantity': data['quantity'],
                        'average_cost_usd': (
                            data['total_cost_usd'] / data['quantity']
                            if data['quantity'] > 0 else Decimal('0.00')
                        ),
                        'average_cost_brl': (
                            data['total_cost_brl'] / data['quantity']
                            if data['quantity'] > 0 else Decimal('0.00')
                        ),
                        'total_cost_usd': data['total_cost_usd'],
                        'total_cost_brl': data['total_cost_brl'],
                        'fifo_lots': data['fifo_lots']
                    })
            
            return holdings_list
            
        except Exception as e:
            logger.error(f"Error calculating holdings: {e}")
            return []
    
    def calculate_correlation(self, returns1, returns2):
        """Calculate correlation between two return series"""
        try:
            if not returns1 or not returns2:
                return Decimal('0.00')
            
            # Ensure equal length
            min_len = min(len(returns1), len(returns2))
            returns1 = returns1[:min_len]
            returns2 = returns2[:min_len]
            
            # Calculate correlation
            correlation = numpy.corrcoef(returns1, returns2)[0, 1]
            return Decimal(str(correlation))
            
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return Decimal('0.00')
    
    def calculate_diversification_score(self, holdings):
        """Calculate portfolio diversification score using HHI"""
        try:
            weights = [h['weight'] for h in holdings]
            
            # Calculate Herfindahl-Hirschman Index
            hhi = sum(w * w for w in weights)
            
            # Convert HHI to 0-100 score (lower HHI = better diversification)
            max_hhi = 1.0  # Single stock portfolio
            min_hhi = 1.0 / len(weights) if weights else 0.0
            
            if max_hhi == min_hhi:
                return Decimal('0.00')
            
            score = (
                (max_hhi - float(hhi)) /
                (max_hhi - min_hhi)
            ) * 100
            
            return Decimal(str(score))
            
        except Exception as e:
            logger.error(f"Error calculating diversification score: {e}")
            return Decimal('0.00')
    
    def calculate_currency_exposure(self, total_value_brl, exchange_rate):
        """Calculate currency exposure and hedging recommendations"""
        try:
            # Calculate USD exposure
            usd_exposure = total_value_brl / exchange_rate
            usd_exposure_pct = (
                (usd_exposure * exchange_rate / total_value_brl) * 100
                if total_value_brl > 0 else Decimal('0.00')
            )
            
            # Generate hedging suggestion
            if usd_exposure_pct > Decimal('70.00'):
                hedge_suggestion = (
                    "Alta exposição ao dólar (>70%). Considere: \n"
                    "1. Aumentar exposição a ativos locais\n"
                    "2. Implementar hedge cambial via contratos futuros\n"
                    "3. Adicionar ETFs de mercado local"
                )
            elif usd_exposure_pct < Decimal('30.00'):
                hedge_suggestion = (
                    "Baixa exposição ao dólar (<30%). Considere: \n"
                    "1. Aumentar diversificação internacional\n"
                    "2. Adicionar ADRs de empresas brasileiras\n"
                    "3. Explorar ETFs internacionais"
                )
            else:
                hedge_suggestion = "Exposição cambial adequada"
            
            return {
                'usd_exposure': usd_exposure,
                'usd_exposure_pct': usd_exposure_pct,
                'hedge_suggestion': hedge_suggestion
            }
            
        except Exception as e:
            logger.error(f"Error calculating currency exposure: {e}")
            return {
                'usd_exposure': Decimal('0.00'),
                'usd_exposure_pct': Decimal('0.00'),
                'hedge_suggestion': "Erro ao calcular exposição cambial"
            }
    
    def calculate_sector_exposure(self, holdings):
        """Calculate sector exposure and concentration"""
        try:
            sector_exposure = {}
            
            for holding in holdings:
                ticker = holding['ticker']
                weight = holding['weight']
                
                # Get sector classification
                sector = self.api_manager.get_sector(ticker)
                if sector:
                    if sector not in sector_exposure:
                        sector_exposure[sector] = Decimal('0.00')
                    sector_exposure[sector] += weight
            
            # Calculate concentration metrics
            max_sector = max(
                sector_exposure.items(),
                key=lambda x: x[1],
                default=('Unknown', Decimal('0.00'))
            )
            
            return {
                'exposures': sector_exposure,
                'max_sector': {
                    'name': max_sector[0],
                    'weight': max_sector[1]
                },
                'concentration_warning': (
                    max_sector[1] > self.MAX_SECTOR_WEIGHT
                )
            }
            
        except Exception as e:
            logger.error(f"Error calculating sector exposure: {e}")
            return {
                'exposures': {},
                'max_sector': {
                    'name': 'Unknown',
                    'weight': Decimal('0.00')
                },
                'concentration_warning': False
            }
    
    def calculate_risk_concentration(self, holdings):
        """Calculate risk concentration metrics"""
        try:
            # Get top holdings by weight
            sorted_holdings = sorted(
                holdings,
                key=lambda x: x['weight'],
                reverse=True
            )
            
            # Calculate concentration metrics
            top_holding = sorted_holdings[0] if sorted_holdings else None
            top_3_weight = sum(
                h['weight'] for h in sorted_holdings[:3]
            )
            top_5_weight = sum(
                h['weight'] for h in sorted_holdings[:5]
            )
            
            return {
                'top_holding': {
                    'ticker': top_holding['ticker'] if top_holding else None,
                    'weight': top_holding['weight'] if top_holding else Decimal('0.00')
                },
                'top_3_weight': top_3_weight,
                'top_5_weight': top_5_weight,
                'concentration_warning': (
                    top_holding and
                    top_holding['weight'] > self.MAX_POSITION_WEIGHT
                )
            }
            
        except Exception as e:
            logger.error(f"Error calculating risk concentration: {e}")
            return {
                'top_holding': {
                    'ticker': None,
                    'weight': Decimal('0.00')
                },
                'top_3_weight': Decimal('0.00'),
                'top_5_weight': Decimal('0.00'),
                'concentration_warning': False
            }
    
    def get_default_metrics(self):
        """Return default risk metrics when calculation fails"""
        return {
            'portfolio_volatility': Decimal('0.00'),
            'portfolio_beta': Decimal('1.00'),
            'value_at_risk_95': Decimal('0.00'),
            'expected_shortfall': Decimal('0.00'),
            'tracking_error': Decimal('0.00'),
            'information_ratio': Decimal('0.00'),
            'sortino_ratio': Decimal('0.00'),
            'diversification_score': Decimal('0.00'),
            'currency_exposure': {
                'usd_exposure': Decimal('0.00'),
                'usd_exposure_pct': Decimal('0.00'),
                'hedge_suggestion': "Erro ao calcular exposição cambial"
            },
            'sector_exposure': {
                'exposures': {},
                'max_sector': {
                    'name': 'Unknown',
                    'weight': Decimal('0.00')
                },
                'concentration_warning': False
            },
            'risk_concentration': {
                'top_holding': {
                    'ticker': None,
                    'weight': Decimal('0.00')
                },
                'top_3_weight': Decimal('0.00'),
                'top_5_weight': Decimal('0.00'),
                'concentration_warning': False
            }
        }


class MarketDataCache:
    """Utility class for caching market data"""
    
    @staticmethod
    def get_cached_quote(ticker):
        """Get cached ADR quote"""
        cache_key = f"adr_quote_{ticker}"
        return cache.get(cache_key)
    
    @staticmethod
    def cache_quote(ticker, quote_data, timeout=60):
        """Cache ADR quote data"""
        cache_key = f"adr_quote_{ticker}"
        cache.set(cache_key, quote_data, timeout)
    
    @staticmethod
    def get_cached_correlation():
        """Get cached correlation data"""
        cache_key = "market_correlation"
        return cache.get(cache_key)
    
    @staticmethod
    def cache_correlation(correlation_data, timeout=3600):
        """Cache correlation data"""
        cache_key = "market_correlation"
        cache.set(cache_key, correlation_data, timeout)


class NotificationService:
    """Service for sending notifications with enhanced error handling and templating"""
    
    # Message templates in Portuguese
    TEMPLATES = {
        'price_alert': {
            'email_subject': 'Alerta de Preço - {ticker}',
            'email_body': """
                Olá {name},

                Seu alerta de preço para {ticker} foi acionado.

                Condição: {condition}
                Valor Alvo: {target_value}
                Preço Atual: {current_price}

                Acesse sua conta para mais detalhes.

                Atenciosamente,
                Equipe Finance API
            """,
            'whatsapp': """
                *Alerta de Preço - {ticker}*

                Condição: {condition}
                Valor Alvo: {target_value}
                Preço Atual: {current_price}

                Acesse o app para mais detalhes.
            """
        },
        'tax_reminder': {
            'email_subject': 'Lembrete de Declaração - ADRs',
            'email_body': """
                Olá {name},

                Este é um lembrete sobre suas operações com ADRs:

                Total de Operações: {total_trades}
                Lucro/Prejuízo: {profit_loss}
                IRRF Pago: {irrf_paid}

                Prazo para Declaração: {deadline}

                Atenciosamente,
                Equipe Finance API
            """,
            'whatsapp': """
                *Lembrete de Declaração - ADRs*

                Operações: {total_trades}
                Resultado: {profit_loss}
                IRRF: {irrf_paid}
                Prazo: {deadline}
            """
        }
    }
    
    def __init__(self):
        from django.conf import settings
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        self.send_mail = send_mail
        self.settings = settings
        self.rate_limiter = {}  # Dict to track notification rates
        
        # Configure requests with retries
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # Initialize Twilio client if credentials are available
        if hasattr(settings, 'TWILIO_ACCOUNT_SID') and hasattr(settings, 'TWILIO_AUTH_TOKEN'):
            self.twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            # Configure Twilio retry settings
            self.twilio_client.http_client.timeout = 5
        else:
            self.twilio_client = None
    
    def _check_rate_limit(self, user_id, channel, max_per_hour=10):
        """Check if user has exceeded rate limit for notification channel"""
        current_time = timezone.now()
        key = f"{user_id}:{channel}"
        
        if key in self.rate_limiter:
            count, last_reset = self.rate_limiter[key]
            # Reset counter if an hour has passed
            if (current_time - last_reset).total_seconds() > 3600:
                self.rate_limiter[key] = (1, current_time)
                return True
            # Check if under limit
            if count < max_per_hour:
                self.rate_limiter[key] = (count + 1, last_reset)
                return True
            return False
        
        # First notification for this user/channel
        self.rate_limiter[key] = (1, current_time)
        return True
    
    def _format_message(self, template_key, template_type, context):
        """Format message using template and context"""
        try:
            template = self.TEMPLATES[template_key][template_type]
            return template.format(**context)
        except KeyError as e:
            logger.error(f"Template formatting error: Missing key {e}")
            raise ValueError(f"Invalid template or context: {e}")
    
    @staticmethod
    def send_price_alert(alert, current_price):
        """Send price alert notification with retries and rate limiting"""
        try:
            service = NotificationService()
            
            # Check rate limit
            if not service._check_rate_limit(alert.user.id, alert.notification_channel):
                logger.warning(f"Rate limit exceeded for user {alert.user.id} on {alert.notification_channel}")
                return False
            
            # Format values
            formatted_target = (
                f"R${alert.target_value:.2f}"
                if alert.condition_type != 'change_percent'
                else f"{alert.target_value}%"
            )
            formatted_current = f"R${current_price:.2f}"
            
            # Prepare context for templates
            context = {
                'name': alert.user.first_name or alert.user.username,
                'ticker': alert.ticker,
                'condition': alert.get_condition_type_display(),
                'target_value': formatted_target,
                'current_price': formatted_current
            }
            
            # Send notification based on channel
            if alert.notification_channel == 'email':
                return service._send_email_alert(alert, context)
            elif alert.notification_channel == 'webhook':
                return service._send_webhook_alert(alert, context)
            elif alert.notification_channel == 'whatsapp':
                return service._send_whatsapp_alert(alert, context)
            
        except Exception as e:
            logger.error(f"Error sending notification for alert {alert.id}: {e}")
            return False
    
    def _send_email_alert(self, alert, context):
        """Send email alert with retries"""
        try:
            subject = self._format_message('price_alert', 'email_subject', context)
            message = self._format_message('price_alert', 'email_body', context)
            
            for attempt in range(3):  # Try up to 3 times
                try:
                    sent = self.send_mail(
                        subject=subject,
                        message=message,
                        from_email=self.settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[alert.user.email],
                        fail_silently=False
                    )
                    
                    if sent:
                        logger.info(f"Email alert sent for {alert.ticker} to {alert.user.email}")
                        return True
                    
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        raise
                    logger.warning(f"Email retry {attempt + 1} for {alert.id}: {e}")
                    time.sleep(1)  # Wait before retry
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
            return False
    
    def _send_webhook_alert(self, alert, context):
        """Send webhook alert with configured retries"""
        try:
            payload = {
                'ticker': alert.ticker,
                'condition': alert.condition_type,
                'target_value': str(alert.target_value),
                'current_price': context['current_price'],
                'user_id': str(alert.user.id),
                'timestamp': timezone.now().isoformat()
            }
            
            response = self.session.post(
                alert.webhook_url,
                json=payload,
                timeout=5,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook alert sent successfully for {alert.id}")
                return True
            
            logger.error(f"Webhook failed with status {response.status_code}: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
            return False
    
    def _send_whatsapp_alert(self, alert, context):
        """Send WhatsApp alert with retries"""
        try:
            if not self.twilio_client:
                logger.error("Twilio client not configured")
                return False
            
            if not alert.user.whatsapp_number:
                logger.error(f"No WhatsApp number for user {alert.user.id}")
                return False
            
            message_body = self._format_message('price_alert', 'whatsapp', context)
            
            for attempt in range(3):  # Try up to 3 times
                try:
                    message = self.twilio_client.messages.create(
                        body=message_body,
                        from_=f"whatsapp:{self.settings.TWILIO_WHATSAPP_NUMBER}",
                        to=f"whatsapp:{alert.user.whatsapp_number}"
                    )
                    
                    if message.sid:
                        logger.info(f"WhatsApp alert sent for {alert.ticker} to {alert.user.whatsapp_number}")
                        return True
                    
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        raise
                    logger.warning(f"WhatsApp retry {attempt + 1} for {alert.id}: {e}")
                    time.sleep(1)  # Wait before retry
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp alert: {e}")
            return False


class DataValidator:
    """Utility class for data validation"""
    
    @staticmethod
    def validate_ticker(ticker):
        """Validate if ticker is a supported ADR"""
        from django.conf import settings
        supported_adrs = getattr(settings, 'SUPPORTED_ADRS', [])
        return ticker.upper() in supported_adrs
    
    @staticmethod
    def validate_price(price):
        """Validate price is positive"""
        try:
            price_decimal = Decimal(str(price))
            return price_decimal > 0
        except:
            return False
    
    @staticmethod
    def validate_date_range(start_date, end_date):
        """Validate date range"""
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        return start_date <= end_date and end_date <= date.today()


class InsightGenerator:
    """Generate insights and recommendations"""
    
    @staticmethod
    def generate_correlation_insights(correlation_data):
        """Generate insights from correlation data"""
        insights = []
        
        corr_30d = float(correlation_data['correlation_30d'])
        corr_7d = float(correlation_data['correlation_7d'])
        
        if abs(corr_30d) > 0.7:
            insights.append(
                f"Alta correlação de {corr_30d:.2f} entre S&P 500 e Ibovespa nos últimos 30 dias"
            )
        elif abs(corr_30d) < 0.3:
            insights.append(
                f"Baixa correlação de {corr_30d:.2f} indica movimentos independentes dos mercados"
            )
        
        if abs(corr_7d - corr_30d) > 0.2:
            if corr_7d > corr_30d:
                insights.append("Correlação aumentou significativamente na última semana")
            else:
                insights.append("Correlação diminuiu significativamente na última semana")
        
        # Market direction insights
        sp500_return = float(correlation_data['sp500_return'])
        ibovespa_return = float(correlation_data['ibovespa_return'])
        
        if sp500_return > 0 and ibovespa_return > 0:
            insights.append("Ambos os mercados estão em alta")
        elif sp500_return < 0 and ibovespa_return < 0:
            insights.append("Ambos os mercados estão em baixa")
        else:
            insights.append("Mercados se movendo em direções opostas")
        
        return insights
    
    @staticmethod
    def generate_portfolio_recommendations(portfolio_summary, market_data):
        """Generate portfolio recommendations"""
        recommendations = []
        
        if portfolio_summary['holdings_count'] == 0:
            recommendations.append("Considere diversificar seu portfólio com ADRs brasileiras")
            return recommendations
        
        # Concentration risk
        if portfolio_summary['holdings_count'] < 3:
            recommendations.append("Considere diversificar mais seu portfólio")
        
        # Performance analysis
        if portfolio_summary['total_gain_loss_percent'] < -10:
            recommendations.append("Portfólio com perdas significativas - considere rebalanceamento")
        elif portfolio_summary['total_gain_loss_percent'] > 20:
            recommendations.append("Excelente performance - considere realizar alguns lucros")
        
        return recommendations 