import time
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from .models import APIUsageLog
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class RateLimitMiddleware(MiddlewareMixin):
    """
    Middleware to handle rate limiting and API usage tracking
    """
    
    def process_request(self, request):
        """
        Process incoming request for rate limiting
        """
        # Only apply to API endpoints
        if not request.path.startswith('/api/'):
            return None
        
        # Get user from API key
        user = self.get_user_from_request(request)
        
        if user:
            # Check rate limit
            if not user.can_make_request():
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': f'You have exceeded the daily limit for your {user.plan} plan',
                    'plan': user.plan,
                    'daily_requests': user.daily_requests
                }, status=429)
            
            # Store request start time for response time calculation
            request._start_time = time.time()
            request._api_user = user
        
        return None
    
    def process_response(self, request, response):
        """
        Process response to log API usage and increment request counter
        """
        # Only process API endpoints
        if not request.path.startswith('/api/'):
            return response
        
        user = getattr(request, '_api_user', None)
        
        if user:
            # Increment request counter
            user.increment_requests()
            
            # Log API usage
            self.log_api_usage(request, response, user)
        
        return response
    
    def get_user_from_request(self, request):
        """
        Extract user from API key in request
        """
        try:
            # Try to get API key from various sources
            api_key = None
            
            # Authorization header
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                api_key = auth_header[7:]
            
            # X-API-Key header
            if not api_key:
                api_key = request.META.get('HTTP_X_API_KEY')
            
            # Query parameter (for testing)
            if not api_key:
                api_key = request.GET.get('api_key')
            
            if api_key:
                return User.objects.get(api_key=api_key)
            
        except User.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error getting user from request: {e}")
        
        return None
    
    def log_api_usage(self, request, response, user):
        """
        Log API usage for analytics
        """
        try:
            response_time = 0
            if hasattr(request, '_start_time'):
                response_time = int((time.time() - request._start_time) * 1000)
            
            # Get client IP
            ip_address = self.get_client_ip(request)
            
            # Create usage log entry
            APIUsageLog.objects.create(
                user=user,
                endpoint=request.path,
                method=request.method,
                status_code=response.status_code,
                response_time_ms=response_time,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]  # Truncate long user agents
            )
            
        except Exception as e:
            logger.error(f"Error logging API usage: {e}")
    
    def get_client_ip(self, request):
        """
        Get the client's IP address
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CacheMiddleware(MiddlewareMixin):
    """
    Middleware to handle caching for API responses
    """
    
    def process_request(self, request):
        """
        Check if we have a cached response for this request
        """
        # Only cache GET requests to API endpoints
        if request.method != 'GET' or not request.path.startswith('/api/'):
            return None
        
        # Generate cache key
        cache_key = self.generate_cache_key(request)
        
        # Try to get cached response
        cached_response = cache.get(cache_key)
        
        if cached_response:
            logger.info(f"Cache hit for {request.path}")
            return JsonResponse(cached_response)
        
        return None
    
    def process_response(self, request, response):
        """
        Cache successful API responses
        """
        # Only cache successful GET requests to API endpoints
        if (request.method != 'GET' or 
            not request.path.startswith('/api/') or 
            response.status_code != 200):
            return response
        
        try:
            # Generate cache key
            cache_key = self.generate_cache_key(request)
            
            # Determine cache timeout based on endpoint
            timeout = self.get_cache_timeout(request.path)
            
            if timeout > 0 and hasattr(response, 'data'):
                # Cache the response data
                cache.set(cache_key, response.data, timeout)
                logger.info(f"Cached response for {request.path} (timeout: {timeout}s)")
        
        except Exception as e:
            logger.error(f"Error caching response: {e}")
        
        return response
    
    def generate_cache_key(self, request):
        """
        Generate a cache key for the request
        """
        # Include path and query parameters in cache key
        query_string = request.GET.urlencode()
        cache_key = f"api_cache:{request.path}"
        
        if query_string:
            cache_key += f":{query_string}"
        
        return cache_key
    
    def get_cache_timeout(self, path):
        """
        Determine cache timeout based on endpoint
        """
        cache_timeouts = {
            '/api/adrs/': 60,  # 1 minute for ADR quotes
            '/api/correlacao/': 3600,  # 1 hour for correlation data
            '/api/dashboard/': 300,  # 5 minutes for dashboard data
        }
        
        for endpoint, timeout in cache_timeouts.items():
            if path.startswith(endpoint):
                return timeout
        
        return 0  # No caching by default


class SecurityMiddleware(MiddlewareMixin):
    """
    Additional security middleware for API endpoints
    """
    
    def process_request(self, request):
        """
        Add security checks for API requests
        """
        # Only apply to API endpoints
        if not request.path.startswith('/api/'):
            return None
        
        # Check for suspicious patterns
        if self.is_suspicious_request(request):
            logger.warning(f"Suspicious request detected: {request.path} from {self.get_client_ip(request)}")
            return JsonResponse({
                'error': 'Request blocked',
                'message': 'Suspicious activity detected'
            }, status=403)
        
        return None
    
    def process_response(self, request, response):
        """
        Add security headers to API responses
        """
        if request.path.startswith('/api/'):
            # Add security headers
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response
    
    def is_suspicious_request(self, request):
        """
        Check if request shows suspicious patterns
        """
        # Check for common attack patterns
        suspicious_patterns = [
            'script', 'javascript:', 'vbscript:', 'onload', 'onerror',
            'eval(', 'alert(', 'document.cookie', 'window.location',
            '../', '..\\', '/etc/passwd', '/proc/', 'cmd.exe'
        ]
        
        # Check query parameters
        query_string = request.GET.urlencode().lower()
        for pattern in suspicious_patterns:
            if pattern in query_string:
                return True
        
        # Check user agent for common bot patterns
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        bot_patterns = ['bot', 'crawler', 'spider', 'scraper']
        
        # Allow legitimate bots but log them
        if any(pattern in user_agent for pattern in bot_patterns):
            logger.info(f"Bot detected: {user_agent}")
        
        return False
    
    def get_client_ip(self, request):
        """
        Get the client's IP address
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip 