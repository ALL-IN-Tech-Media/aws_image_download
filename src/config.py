"""
Configuration management for AWS Lambda image processing
Handles environment variables and application settings
"""

import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class Config:
    """Configuration class for AWS Lambda image processor"""
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        
        # S3 Configuration
        self.INPUT_BUCKET = self._get_env_var('INPUT_BUCKET', 'tiktok-image-input')
        self.OUTPUT_BUCKET = self._get_env_var('OUTPUT_BUCKET', 'tiktok-image-output')
        self.TEMP_BUCKET = self._get_env_var('TEMP_BUCKET', 'tiktok-image-temp')
        
        # SQS Configuration
        self.SQS_QUEUE_URL = self._get_env_var('SQS_QUEUE_URL')
        self.SQS_DLQ_URL = self._get_env_var('SQS_DLQ_URL')
        
        # AWS Region (AWS_REGION is reserved in Lambda, use AWS_DEFAULT_REGION)
        self.AWS_REGION = self._get_env_var('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-2'))
        
        # Processing Configuration
        self.DEFAULT_ROWS = int(self._get_env_var('DEFAULT_ROWS', '5'))
        self.DEFAULT_COLS = int(self._get_env_var('DEFAULT_COLS', '7'))
        self.DEFAULT_QUALITY = int(self._get_env_var('DEFAULT_QUALITY', '95'))
        self.DEFAULT_MAX_WORKERS = int(self._get_env_var('DEFAULT_MAX_WORKERS', '8'))
        self.DEFAULT_TIMEOUT = int(self._get_env_var('DEFAULT_TIMEOUT', '30'))
        self.DEFAULT_MAX_RETRIES = int(self._get_env_var('DEFAULT_MAX_RETRIES', '3'))
        self.DEFAULT_MAX_IMAGES_PER_CREATOR = int(self._get_env_var('DEFAULT_MAX_IMAGES_PER_CREATOR', '35'))
        
        # Image Processing Configuration
        self.MIN_IMAGE_SIZE = int(self._get_env_var('MIN_IMAGE_SIZE', '50'))
        self.MAX_IMAGE_SIZE = int(self._get_env_var('MAX_IMAGE_SIZE', '800'))
        self.MIN_COLLAGE_SIZE = int(self._get_env_var('MIN_COLLAGE_SIZE', '200'))
        
        # Memory and Performance Configuration
        self.MEMORY_WARNING_THRESHOLD = float(self._get_env_var('MEMORY_WARNING_THRESHOLD', '80.0'))  # Percentage
        self.MEMORY_CRITICAL_THRESHOLD = float(self._get_env_var('MEMORY_CRITICAL_THRESHOLD', '90.0'))  # Percentage
        self.MAX_CONCURRENT_DOWNLOADS = int(self._get_env_var('MAX_CONCURRENT_DOWNLOADS', '8'))
        
        # S3 Configuration Options
        self.S3_PUBLIC_READ = self._get_bool_env_var('S3_PUBLIC_READ', False)
        self.S3_PRESIGNED_URL_EXPIRATION = int(self._get_env_var('S3_PRESIGNED_URL_EXPIRATION', '3600'))  # 1 hour
        
        # Logging Configuration
        self.LOG_LEVEL = self._get_env_var('LOG_LEVEL', 'INFO')
        self.ENABLE_DEBUG_LOGGING = self._get_bool_env_var('ENABLE_DEBUG_LOGGING', False)
        
        # Rate Limiting Configuration
        self.RATE_LIMIT_ENABLED = self._get_bool_env_var('RATE_LIMIT_ENABLED', True)
        self.RATE_LIMIT_REQUESTS_PER_SECOND = float(self._get_env_var('RATE_LIMIT_REQUESTS_PER_SECOND', '10.0'))
        self.RATE_LIMIT_BURST = int(self._get_env_var('RATE_LIMIT_BURST', '20'))
        
        # Error Handling Configuration
        self.MAX_RETRY_ATTEMPTS = int(self._get_env_var('MAX_RETRY_ATTEMPTS', '3'))
        self.RETRY_BACKOFF_FACTOR = float(self._get_env_var('RETRY_BACKOFF_FACTOR', '2.0'))
        self.RETRY_MAX_DELAY = int(self._get_env_var('RETRY_MAX_DELAY', '60'))  # seconds
        
        # Lambda-specific Configuration
        self.LAMBDA_FUNCTION_NAME = self._get_env_var('AWS_LAMBDA_FUNCTION_NAME', 'image-collage-processor')
        self.LAMBDA_REQUEST_ID = os.environ.get('AWS_LAMBDA_REQUEST_ID')
        self.LAMBDA_LOG_GROUP_NAME = os.environ.get('AWS_LAMBDA_LOG_GROUP_NAME')
        self.LAMBDA_LOG_STREAM_NAME = os.environ.get('AWS_LAMBDA_LOG_STREAM_NAME')
        
        # TikTok CDN Configuration
        self.TIKTOK_CDN_DOMAINS = [
            'tiktokcdn-us.com',
            'tiktokcdn.com',
            'muscdn.com'
        ]
        
        # User Agent for HTTP requests
        self.USER_AGENT = self._get_env_var(
            'USER_AGENT',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Validate critical configuration
        self._validate_config()
        
        # Log configuration summary
        self._log_config_summary()
    
    def _get_env_var(self, var_name: str, default: Optional[str] = None) -> str:
        """
        Get environment variable with optional default
        
        Args:
            var_name: Environment variable name
            default: Default value if variable not found
            
        Returns:
            Environment variable value or default
            
        Raises:
            ValueError: If required variable is missing and no default provided
        """
        value = os.environ.get(var_name, default)
        if value is None:
            raise ValueError(f"Required environment variable '{var_name}' is not set")
        return value
    
    def _get_bool_env_var(self, var_name: str, default: bool = False) -> bool:
        """
        Get boolean environment variable
        
        Args:
            var_name: Environment variable name
            default: Default boolean value
            
        Returns:
            Boolean value
        """
        value = os.environ.get(var_name, str(default)).lower()
        return value in ('true', '1', 'yes', 'on', 'enabled')
    
    def _validate_config(self):
        """Validate critical configuration parameters"""
        errors = []
        
        # Validate S3 bucket names
        if not self.INPUT_BUCKET:
            errors.append("INPUT_BUCKET is required")
        if not self.OUTPUT_BUCKET:
            errors.append("OUTPUT_BUCKET is required")
        
        # Validate processing parameters
        if self.DEFAULT_ROWS <= 0:
            errors.append("DEFAULT_ROWS must be positive")
        if self.DEFAULT_COLS <= 0:
            errors.append("DEFAULT_COLS must be positive")
        if not 1 <= self.DEFAULT_QUALITY <= 100:
            errors.append("DEFAULT_QUALITY must be between 1 and 100")
        if self.DEFAULT_MAX_WORKERS <= 0:
            errors.append("DEFAULT_MAX_WORKERS must be positive")
        if self.DEFAULT_TIMEOUT <= 0:
            errors.append("DEFAULT_TIMEOUT must be positive")
        
        # Validate memory thresholds
        if not 0 <= self.MEMORY_WARNING_THRESHOLD <= 100:
            errors.append("MEMORY_WARNING_THRESHOLD must be between 0 and 100")
        if not 0 <= self.MEMORY_CRITICAL_THRESHOLD <= 100:
            errors.append("MEMORY_CRITICAL_THRESHOLD must be between 0 and 100")
        if self.MEMORY_WARNING_THRESHOLD >= self.MEMORY_CRITICAL_THRESHOLD:
            errors.append("MEMORY_WARNING_THRESHOLD must be less than MEMORY_CRITICAL_THRESHOLD")
        
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def _log_config_summary(self):
        """Log configuration summary for debugging"""
        if self.ENABLE_DEBUG_LOGGING:
            logger.info("Configuration Summary:")
            logger.info(f"  S3 Buckets: input={self.INPUT_BUCKET}, output={self.OUTPUT_BUCKET}, temp={self.TEMP_BUCKET}")
            logger.info(f"  SQS Queue: {self.SQS_QUEUE_URL}")
            logger.info(f"  Processing: {self.DEFAULT_ROWS}x{self.DEFAULT_COLS}, quality={self.DEFAULT_QUALITY}")
            logger.info(f"  Workers: {self.DEFAULT_MAX_WORKERS}, timeout={self.DEFAULT_TIMEOUT}s")
            logger.info(f"  Memory thresholds: warning={self.MEMORY_WARNING_THRESHOLD}%, critical={self.MEMORY_CRITICAL_THRESHOLD}%")
    
    def get_processing_config(self) -> Dict[str, Any]:
        """
        Get default processing configuration
        
        Returns:
            Dictionary with default processing parameters
        """
        return {
            'group_by_creator': True,
            'rows': self.DEFAULT_ROWS,
            'cols': self.DEFAULT_COLS,
            'max_images_per_creator': self.DEFAULT_MAX_IMAGES_PER_CREATOR,
            'quality': self.DEFAULT_QUALITY,
            'max_workers': self.DEFAULT_MAX_WORKERS,
            'timeout': self.DEFAULT_TIMEOUT,
            'max_retries': self.DEFAULT_MAX_RETRIES
        }
    
    def get_s3_config(self) -> Dict[str, Any]:
        """
        Get S3 configuration
        
        Returns:
            Dictionary with S3 configuration parameters
        """
        return {
            'input_bucket': self.INPUT_BUCKET,
            'output_bucket': self.OUTPUT_BUCKET,
            'temp_bucket': self.TEMP_BUCKET,
            'public_read': self.S3_PUBLIC_READ,
            'presigned_url_expiration': self.S3_PRESIGNED_URL_EXPIRATION
        }
    
    def get_sqs_config(self) -> Dict[str, Any]:
        """
        Get SQS configuration
        
        Returns:
            Dictionary with SQS configuration parameters
        """
        return {
            'queue_url': self.SQS_QUEUE_URL,
            'dlq_url': self.SQS_DLQ_URL
        }
    
    def get_image_processing_config(self) -> Dict[str, Any]:
        """
        Get image processing configuration
        
        Returns:
            Dictionary with image processing parameters
        """
        return {
            'min_image_size': self.MIN_IMAGE_SIZE,
            'max_image_size': self.MAX_IMAGE_SIZE,
            'min_collage_size': self.MIN_COLLAGE_SIZE,
            'user_agent': self.USER_AGENT,
            'tiktok_cdn_domains': self.TIKTOK_CDN_DOMAINS
        }
    
    def get_performance_config(self) -> Dict[str, Any]:
        """
        Get performance configuration
        
        Returns:
            Dictionary with performance parameters
        """
        return {
            'memory_warning_threshold': self.MEMORY_WARNING_THRESHOLD,
            'memory_critical_threshold': self.MEMORY_CRITICAL_THRESHOLD,
            'max_concurrent_downloads': self.MAX_CONCURRENT_DOWNLOADS,
            'rate_limit_enabled': self.RATE_LIMIT_ENABLED,
            'rate_limit_rps': self.RATE_LIMIT_REQUESTS_PER_SECOND,
            'rate_limit_burst': self.RATE_LIMIT_BURST
        }
    
    def get_error_handling_config(self) -> Dict[str, Any]:
        """
        Get error handling configuration
        
        Returns:
            Dictionary with error handling parameters
        """
        return {
            'max_retry_attempts': self.MAX_RETRY_ATTEMPTS,
            'retry_backoff_factor': self.RETRY_BACKOFF_FACTOR,
            'retry_max_delay': self.RETRY_MAX_DELAY
        }
    
    def is_lambda_environment(self) -> bool:
        """
        Check if running in AWS Lambda environment
        
        Returns:
            True if running in Lambda, False otherwise
        """
        return self.LAMBDA_REQUEST_ID is not None
    
    def get_lambda_context_info(self) -> Dict[str, Any]:
        """
        Get Lambda context information
        
        Returns:
            Dictionary with Lambda context data
        """
        return {
            'function_name': self.LAMBDA_FUNCTION_NAME,
            'request_id': self.LAMBDA_REQUEST_ID,
            'log_group_name': self.LAMBDA_LOG_GROUP_NAME,
            'log_stream_name': self.LAMBDA_LOG_STREAM_NAME,
            'aws_region': self.AWS_REGION
        }
    
    def update_from_message(self, message_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update configuration from SQS message
        
        Args:
            message_config: Configuration from SQS message
            
        Returns:
            Merged configuration dictionary
        """
        base_config = self.get_processing_config()
        
        # Update with message-specific configuration
        for key, value in message_config.items():
            if key in base_config:
                base_config[key] = value
            else:
                logger.warning(f"Unknown configuration parameter in message: {key}")
        
        # Validate updated configuration
        self._validate_message_config(base_config)
        
        return base_config
    
    def _validate_message_config(self, config: Dict[str, Any]):
        """
        Validate configuration from message
        
        Args:
            config: Configuration dictionary to validate
        """
        errors = []
        
        # Validate rows and cols
        if config.get('rows', 0) <= 0:
            errors.append("rows must be positive")
        if config.get('cols', 0) <= 0:
            errors.append("cols must be positive")
        
        # Validate quality
        quality = config.get('quality', 95)
        if not 1 <= quality <= 100:
            errors.append("quality must be between 1 and 100")
        
        # Validate workers
        max_workers = config.get('max_workers', 8)
        if max_workers <= 0:
            errors.append("max_workers must be positive")
        if max_workers > 20:  # Reasonable upper limit
            errors.append("max_workers should not exceed 20")
        
        # Validate timeout
        timeout = config.get('timeout', 30)
        if timeout <= 0:
            errors.append("timeout must be positive")
        if timeout > 300:  # 5 minutes max
            errors.append("timeout should not exceed 300 seconds")
        
        if errors:
            error_msg = "Message configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def __str__(self) -> str:
        """String representation of configuration"""
        return (
            f"Config(input_bucket={self.INPUT_BUCKET}, "
            f"output_bucket={self.OUTPUT_BUCKET}, "
            f"processing={self.DEFAULT_ROWS}x{self.DEFAULT_COLS}, "
            f"quality={self.DEFAULT_QUALITY})"
        )
