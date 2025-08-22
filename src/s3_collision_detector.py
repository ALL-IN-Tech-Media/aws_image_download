"""
S3 collision detection module for preventing duplicate collage generation
Checks for existing collages and implements deterministic naming
"""

import boto3
import logging
from typing import Dict, Any, Optional, List, Tuple
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime

from config import Config
from content_hasher import ContentHasher

logger = logging.getLogger(__name__)

class S3CollisionDetector:
    """S3-based collision detection for preventing duplicate collages"""
    
    def __init__(self, config: Config):
        """
        Initialize S3 collision detector
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.s3_config = config.get_s3_config()
        self.dedup_config = config.get_deduplication_config()
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client('s3', region_name=config.AWS_REGION)
            logger.info(f"Initialized S3 collision detector for region: {config.AWS_REGION}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise
        
        # Initialize content hasher
        self.content_hasher = ContentHasher(
            algorithm=self.dedup_config['content_hash_algorithm']
        )
        
        self.output_bucket = self.s3_config['output_bucket']
    
    def generate_deterministic_s3_key(self, creator_name: str, 
                                    image_urls: List[str],
                                    output_prefix: str = "",
                                    processing_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate deterministic S3 key for creator collage
        
        Args:
            creator_name: Name of the creator
            image_urls: List of image URLs for the creator
            output_prefix: S3 key prefix
            processing_config: Optional processing configuration
            
        Returns:
            Deterministic S3 key
        """
        try:
            # Generate content hash
            content_hash = self.content_hasher.generate_creator_hash(
                creator_name, image_urls, processing_config
            )
            
            # Generate deterministic filename
            filename = self.content_hasher.generate_deterministic_filename(
                creator_name, content_hash, 'jpg'
            )
            
            # Construct full S3 key
            if output_prefix:
                s3_key = f"{output_prefix.rstrip('/')}/collages/{filename}"
            else:
                s3_key = f"collages/{filename}"
            
            logger.debug(f"Generated deterministic S3 key for {creator_name}: {s3_key}")
            
            return s3_key
            
        except Exception as e:
            logger.error(f"Error generating deterministic S3 key for {creator_name}: {e}")
            raise
    
    def check_collage_exists(self, s3_key: str) -> Dict[str, Any]:
        """
        Check if collage already exists in S3
        
        Args:
            s3_key: S3 key to check
            
        Returns:
            Dictionary with existence information
        """
        try:
            # Use HEAD object to check existence without downloading
            response = self.s3_client.head_object(
                Bucket=self.output_bucket,
                Key=s3_key
            )
            
            # Extract metadata
            metadata = {
                'exists': True,
                's3_key': s3_key,
                'size_bytes': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag', '').strip('"'),
                'content_type': response.get('ContentType'),
                'metadata': response.get('Metadata', {})
            }
            
            logger.info(f"Collage exists: {s3_key} (size: {metadata['size_bytes']} bytes)")
            
            return metadata
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Object does not exist
                return {
                    'exists': False,
                    's3_key': s3_key,
                    'reason': 'Object not found'
                }
            else:
                logger.error(f"Error checking S3 object existence: {e}")
                return {
                    'exists': False,
                    's3_key': s3_key,
                    'error': str(e),
                    'reason': 'Error checking existence'
                }
        except Exception as e:
            logger.error(f"Unexpected error checking S3 object existence: {e}")
            return {
                'exists': False,
                's3_key': s3_key,
                'error': str(e),
                'reason': 'Unexpected error'
            }
    
    def find_existing_collages_for_creator(self, creator_name: str,
                                         output_prefix: str = "") -> List[Dict[str, Any]]:
        """
        Find all existing collages for a specific creator
        
        Args:
            creator_name: Name of the creator
            output_prefix: S3 key prefix to search within
            
        Returns:
            List of existing collage information
        """
        try:
            # Sanitize creator name for search
            safe_creator_name = "".join(c for c in creator_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_creator_name = safe_creator_name.replace(' ', '_').lower()
            
            # Construct search prefix
            if output_prefix:
                search_prefix = f"{output_prefix.rstrip('/')}/collages/{safe_creator_name}_collage_"
            else:
                search_prefix = f"collages/{safe_creator_name}_collage_"
            
            # List objects with prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.output_bucket,
                Prefix=search_prefix,
                MaxKeys=100  # Reasonable limit
            )
            
            existing_collages = []
            
            for obj in response.get('Contents', []):
                collage_info = {
                    's3_key': obj['Key'],
                    'size_bytes': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag'].strip('"')
                }
                existing_collages.append(collage_info)
            
            logger.info(f"Found {len(existing_collages)} existing collages for creator {creator_name}")
            
            return existing_collages
            
        except Exception as e:
            logger.error(f"Error finding existing collages for creator {creator_name}: {e}")
            return []
    
    def should_skip_processing(self, creator_name: str, image_urls: List[str],
                             output_prefix: str = "",
                             processing_config: Optional[Dict[str, Any]] = None,
                             force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Determine if processing should be skipped due to existing collage
        
        Args:
            creator_name: Name of the creator
            image_urls: List of image URLs for the creator
            output_prefix: S3 key prefix
            processing_config: Processing configuration
            force_reprocess: Force reprocessing even if collage exists
            
        Returns:
            Dictionary with skip decision and reasoning
        """
        try:
            # Check if deduplication is enabled
            if not self.dedup_config['enable_deduplication']:
                return {
                    'should_skip': False,
                    'reason': 'Deduplication disabled',
                    'existing_collage': None
                }
            
            # Force reprocess overrides collision detection
            if force_reprocess or self.dedup_config['force_reprocess']:
                return {
                    'should_skip': False,
                    'reason': 'Force reprocess enabled',
                    'existing_collage': None
                }
            
            # Generate deterministic S3 key
            s3_key = self.generate_deterministic_s3_key(
                creator_name, image_urls, output_prefix, processing_config
            )
            
            # Check if exact collage exists
            existence_check = self.check_collage_exists(s3_key)
            
            if existence_check['exists']:
                # Validate collage quality (size check)
                size_bytes = existence_check.get('size_bytes', 0)
                
                # Minimum size check (e.g., 100KB for a valid collage)
                min_size = 100 * 1024  # 100KB
                if size_bytes < min_size:
                    return {
                        'should_skip': False,
                        'reason': f'Existing collage too small ({size_bytes} bytes)',
                        'existing_collage': existence_check,
                        'reprocess_reason': 'quality_check_failed'
                    }
                
                return {
                    'should_skip': True,
                    'reason': 'Identical collage already exists',
                    'existing_collage': existence_check,
                    'content_hash_match': True
                }
            
            # Check for any existing collages for this creator (different content)
            existing_collages = self.find_existing_collages_for_creator(
                creator_name, output_prefix
            )
            
            if existing_collages:
                return {
                    'should_skip': False,
                    'reason': 'Creator has different content, will create new collage',
                    'existing_collages': existing_collages,
                    'content_has_changed': True
                }
            
            # No existing collages found
            return {
                'should_skip': False,
                'reason': 'No existing collages found',
                'existing_collage': None
            }
            
        except Exception as e:
            logger.error(f"Error determining skip status for creator {creator_name}: {e}")
            # On error, default to not skipping to ensure processing continues
            return {
                'should_skip': False,
                'reason': f'Error in collision detection: {str(e)}',
                'error': True
            }
    
    def get_collage_metadata(self, s3_key: str) -> Dict[str, Any]:
        """
        Get detailed metadata for existing collage
        
        Args:
            s3_key: S3 key of the collage
            
        Returns:
            Dictionary with detailed collage metadata
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.output_bucket,
                Key=s3_key
            )
            
            metadata = {
                's3_key': s3_key,
                'bucket': self.output_bucket,
                'size_bytes': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag', '').strip('"'),
                'content_type': response.get('ContentType'),
                'storage_class': response.get('StorageClass', 'STANDARD'),
                'custom_metadata': response.get('Metadata', {}),
                'cache_control': response.get('CacheControl'),
                'content_encoding': response.get('ContentEncoding'),
                'expires': response.get('Expires')
            }
            
            # Try to parse creator name from S3 key
            key_parts = s3_key.split('/')
            if key_parts:
                filename = key_parts[-1]
                if '_collage_' in filename:
                    creator_part = filename.split('_collage_')[0]
                    metadata['creator_name_from_key'] = creator_part
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error getting collage metadata for {s3_key}: {e}")
            return {
                's3_key': s3_key,
                'error': str(e)
            }
    
    def cleanup_old_collages(self, creator_name: str, 
                           keep_latest: int = 1,
                           output_prefix: str = "") -> Dict[str, Any]:
        """
        Clean up old collages for creator, keeping only the most recent ones
        
        Args:
            creator_name: Name of the creator
            keep_latest: Number of latest collages to keep
            output_prefix: S3 key prefix
            
        Returns:
            Dictionary with cleanup results
        """
        try:
            # Find all existing collages for creator
            existing_collages = self.find_existing_collages_for_creator(
                creator_name, output_prefix
            )
            
            if len(existing_collages) <= keep_latest:
                return {
                    'creator_name': creator_name,
                    'total_found': len(existing_collages),
                    'deleted_count': 0,
                    'kept_count': len(existing_collages),
                    'message': 'No cleanup needed'
                }
            
            # Sort by last modified date (newest first)
            existing_collages.sort(
                key=lambda x: x['last_modified'], 
                reverse=True
            )
            
            # Identify collages to delete
            to_keep = existing_collages[:keep_latest]
            to_delete = existing_collages[keep_latest:]
            
            deleted_keys = []
            deletion_errors = []
            
            # Delete old collages
            for collage in to_delete:
                try:
                    self.s3_client.delete_object(
                        Bucket=self.output_bucket,
                        Key=collage['s3_key']
                    )
                    deleted_keys.append(collage['s3_key'])
                    logger.info(f"Deleted old collage: {collage['s3_key']}")
                except Exception as e:
                    deletion_errors.append({
                        's3_key': collage['s3_key'],
                        'error': str(e)
                    })
                    logger.error(f"Error deleting collage {collage['s3_key']}: {e}")
            
            return {
                'creator_name': creator_name,
                'total_found': len(existing_collages),
                'deleted_count': len(deleted_keys),
                'kept_count': len(to_keep),
                'deleted_keys': deleted_keys,
                'deletion_errors': deletion_errors,
                'kept_collages': [c['s3_key'] for c in to_keep]
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up old collages for creator {creator_name}: {e}")
            return {
                'creator_name': creator_name,
                'error': str(e),
                'deleted_count': 0
            }
    
    def validate_collage_integrity(self, s3_key: str) -> Dict[str, Any]:
        """
        Validate integrity of existing collage
        
        Args:
            s3_key: S3 key of collage to validate
            
        Returns:
            Dictionary with validation results
        """
        try:
            # Get object metadata
            metadata = self.get_collage_metadata(s3_key)
            
            if 'error' in metadata:
                return {
                    'valid': False,
                    's3_key': s3_key,
                    'reason': 'Could not retrieve metadata',
                    'error': metadata['error']
                }
            
            validation_results = {
                'valid': True,
                's3_key': s3_key,
                'checks': []
            }
            
            # Size validation
            size_bytes = metadata.get('size_bytes', 0)
            min_size = 50 * 1024  # 50KB minimum
            max_size = 50 * 1024 * 1024  # 50MB maximum
            
            if size_bytes < min_size:
                validation_results['valid'] = False
                validation_results['checks'].append({
                    'check': 'minimum_size',
                    'passed': False,
                    'message': f'File too small: {size_bytes} bytes (min: {min_size})'
                })
            elif size_bytes > max_size:
                validation_results['valid'] = False
                validation_results['checks'].append({
                    'check': 'maximum_size',
                    'passed': False,
                    'message': f'File too large: {size_bytes} bytes (max: {max_size})'
                })
            else:
                validation_results['checks'].append({
                    'check': 'size_validation',
                    'passed': True,
                    'message': f'File size OK: {size_bytes} bytes'
                })
            
            # Content type validation
            content_type = metadata.get('content_type', '')
            if content_type not in ['image/jpeg', 'image/jpg']:
                validation_results['valid'] = False
                validation_results['checks'].append({
                    'check': 'content_type',
                    'passed': False,
                    'message': f'Invalid content type: {content_type}'
                })
            else:
                validation_results['checks'].append({
                    'check': 'content_type',
                    'passed': True,
                    'message': f'Content type OK: {content_type}'
                })
            
            # Age validation (optional warning)
            last_modified = metadata.get('last_modified')
            if last_modified:
                age_days = (datetime.utcnow() - last_modified.replace(tzinfo=None)).days
                if age_days > 30:
                    validation_results['checks'].append({
                        'check': 'age_warning',
                        'passed': True,
                        'message': f'Collage is {age_days} days old',
                        'warning': True
                    })
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating collage integrity for {s3_key}: {e}")
            return {
                'valid': False,
                's3_key': s3_key,
                'error': str(e),
                'reason': 'Validation error'
            }
    
    def get_collision_statistics(self, output_prefix: str = "") -> Dict[str, Any]:
        """
        Get statistics about existing collages and potential collisions
        
        Args:
            output_prefix: S3 key prefix to analyze
            
        Returns:
            Dictionary with collision statistics
        """
        try:
            # List all collages in the prefix
            if output_prefix:
                search_prefix = f"{output_prefix.rstrip('/')}/collages/"
            else:
                search_prefix = "collages/"
            
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            total_collages = 0
            total_size_bytes = 0
            creators = set()
            size_distribution = {'small': 0, 'medium': 0, 'large': 0}
            
            for page in paginator.paginate(Bucket=self.output_bucket, Prefix=search_prefix):
                for obj in page.get('Contents', []):
                    total_collages += 1
                    total_size_bytes += obj['Size']
                    
                    # Extract creator name from filename
                    filename = obj['Key'].split('/')[-1]
                    if '_collage_' in filename:
                        creator_name = filename.split('_collage_')[0]
                        creators.add(creator_name)
                    
                    # Size distribution
                    size_mb = obj['Size'] / (1024 * 1024)
                    if size_mb < 1:
                        size_distribution['small'] += 1
                    elif size_mb < 10:
                        size_distribution['medium'] += 1
                    else:
                        size_distribution['large'] += 1
            
            avg_size_mb = (total_size_bytes / (1024 * 1024)) / total_collages if total_collages > 0 else 0
            
            return {
                'total_collages': total_collages,
                'unique_creators': len(creators),
                'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
                'average_size_mb': round(avg_size_mb, 2),
                'size_distribution': size_distribution,
                'collages_per_creator': round(total_collages / len(creators), 2) if creators else 0,
                'search_prefix': search_prefix
            }
            
        except Exception as e:
            logger.error(f"Error getting collision statistics: {e}")
            return {
                'error': str(e),
                'total_collages': 0,
                'unique_creators': 0
            }
