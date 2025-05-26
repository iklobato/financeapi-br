from rest_framework import authentication
from rest_framework import exceptions
from .models import User
import logging

logger = logging.getLogger(__name__)


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class for API key based authentication
    """
    
    def authenticate(self, request):
        """
        Authenticate the request using API key
        """
        api_key = request.META.get('HTTP_AUTHORIZATION')
        
        if not api_key:
            return None
        
        if not api_key.startswith('Bearer '):
            return None
        
        api_key = api_key.split(' ')[1]
        
        try:
            user = User.objects.get(api_key=api_key)
            
            # Check if user can make requests based on their plan
            if not user.can_make_request():
                raise exceptions.AuthenticationFailed('Rate limit exceeded for your plan')
            
            return (user, None)
            
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key')
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise exceptions.AuthenticationFailed('Authentication failed')
    
    def authenticate_header(self, request):
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response, or `None` if the
        authentication scheme should return `403 Permission Denied` responses.
        """
        return 'Bearer' 