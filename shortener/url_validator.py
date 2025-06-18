import re
from urllib.parse import urlparse
import requests
from django.conf import settings

class URLChecker:
    # List of known malicious domains (you can expand this)
    MALICIOUS_DOMAINS = {
        'bit.ly/malware',
        'tinyurl.com/virus',
        'malware.com',
        'phishing-site.com',
        'virus-download.net',
        # Add more known malicious domains
    }
    
    # Suspicious patterns in URLs
    SUSPICIOUS_PATTERNS = [
        r'\.exe$',  # Executable files
        r'\.scr$',  # Screen savers (often malware)
        r'\.bat$',  # Batch files
        r'\.com\.exe$',  # Fake extensions
        r'phishing',
        r'malware',
        r'virus',
        r'trojan',
        r'download.*\.exe',
        r'free.*download.*\.exe',
    ]
    
    @classmethod
    def is_malicious(cls, url):
        """
        Check if URL is potentially malicious
        Returns tuple: (is_malicious: bool, reason: str)
        """
        try:
            parsed_url = urlparse(url.lower())
            domain = parsed_url.netloc
            full_url = url.lower()
            
            # Check against known malicious domains
            if domain in cls.MALICIOUS_DOMAINS:
                return True, f"Domain '{domain}' is in malicious domains list"
            
            # Check for suspicious patterns
            for pattern in cls.SUSPICIOUS_PATTERNS:
                if re.search(pattern, full_url, re.IGNORECASE):
                    return True, f"URL contains suspicious pattern: {pattern}"
            
            # Check for suspicious URL structure
            if cls._has_suspicious_structure(parsed_url):
                return True, "URL has suspicious structure"
            
            return False, "URL appears safe"
            
        except Exception as e:
            # If we can't parse the URL, consider it suspicious
            return True, f"Unable to validate URL: {str(e)}"
    
    @classmethod
    def _has_suspicious_structure(cls, parsed_url):
        """Check for suspicious URL structures"""
        # Multiple subdomains (potential subdomain abuse)
        if parsed_url.netloc.count('.') > 3:
            return True
        
        # Very long URLs (potential obfuscation)
        if len(parsed_url.geturl()) > 500:
            return True
        
        # URLs with IP addresses instead of domains
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
        if re.search(ip_pattern, parsed_url.netloc):
            return True
        
        return False
