"""
Processing state management using DynamoDB
Tracks creator processing status, batch assignments, and deduplication
"""

import boto3
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from botocore.exceptions import ClientError, BotoCoreError
from decimal import Decimal

from config import Config

logger = logging.getLogger(__name__)

class ProcessingState:
    """DynamoDB-based processing state management"""
    
    def __init__(self, config: Config):
        """
        Initialize processing state manager
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.dynamodb_config = config.get_dynamodb_config()
        self.table_name = self.dynamodb_config['table_name']
        
        # Initialize DynamoDB client
        try:
            self.dynamodb = boto3.resource(
                'dynamodb',
                region_name=self.dynamodb_config['aws_region']
            )
            self.table = self.dynamodb.Table(self.table_name)
            logger.info(f"Initialized DynamoDB connection to table: {self.table_name}")
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB connection: {e}")
            raise
    
    def check_creator_processed(self, creator_name: str, 
                              content_hash: Optional[str] = None,
                              processing_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if creator has already been processed
        
        Args:
            creator_name: Name of the creator to check
            content_hash: Optional content hash to compare
            processing_date: Optional specific date to check (defaults to today)
            
        Returns:
            Dictionary with processing status information
        """
        try:
            if not processing_date:
                processing_date = datetime.utcnow().strftime('%Y-%m-%d')
            
            # Query for creator's processing records
            response = self.table.query(
                KeyConditionExpression='creator_name = :creator_name',
                ExpressionAttributeValues={
                    ':creator_name': creator_name
                },
                ScanIndexForward=False,  # Most recent first
                Limit=10  # Get last 10 processing records
            )
            
            items = response.get('Items', [])
            
            if not items:
                return {
                    'processed': False,
                    'reason': 'No processing records found',
                    'latest_record': None
                }
            
            # Check most recent record
            latest_record = items[0]
            latest_status = latest_record.get('status')
            latest_hash = latest_record.get('content_hash')
            
            # If content hash provided, compare for changes
            if content_hash and latest_hash:
                if content_hash == latest_hash and latest_status == 'completed':
                    return {
                        'processed': True,
                        'reason': 'Same content already processed successfully',
                        'latest_record': latest_record,
                        'content_changed': False
                    }
                elif content_hash != latest_hash:
                    return {
                        'processed': False,
                        'reason': 'Content has changed since last processing',
                        'latest_record': latest_record,
                        'content_changed': True
                    }
            
            # Check if successfully completed today
            if (latest_record.get('processing_date') == processing_date and 
                latest_status == 'completed'):
                return {
                    'processed': True,
                    'reason': 'Already processed successfully today',
                    'latest_record': latest_record,
                    'content_changed': False
                }
            
            # Check if currently processing
            if latest_status == 'processing':
                processing_time = datetime.fromisoformat(latest_record.get('created_at', ''))
                time_diff = datetime.utcnow() - processing_time
                
                # Consider stale after 30 minutes
                if time_diff > timedelta(minutes=30):
                    return {
                        'processed': False,
                        'reason': 'Previous processing appears stale',
                        'latest_record': latest_record,
                        'stale_processing': True
                    }
                else:
                    return {
                        'processed': True,
                        'reason': 'Currently being processed',
                        'latest_record': latest_record,
                        'currently_processing': True
                    }
            
            return {
                'processed': False,
                'reason': 'Previous processing failed or incomplete',
                'latest_record': latest_record
            }
            
        except Exception as e:
            logger.error(f"Error checking processing status for creator {creator_name}: {e}")
            return {
                'processed': False,
                'reason': f'Error checking status: {str(e)}',
                'error': True
            }
    
    def create_processing_record(self, creator_name: str, batch_id: str,
                               content_hash: str, image_count: int,
                               processing_config: Dict[str, Any]) -> bool:
        """
        Create new processing record for creator
        
        Args:
            creator_name: Name of the creator
            batch_id: ID of the batch processing this creator
            content_hash: Hash of creator's content
            image_count: Number of images being processed
            processing_config: Processing configuration used
            
        Returns:
            True if record created successfully
        """
        try:
            current_time = datetime.utcnow()
            processing_date = current_time.strftime('%Y-%m-%d')
            timestamp = current_time.isoformat()
            
            # Calculate TTL (30 days from now)
            ttl_time = current_time + timedelta(days=30)
            ttl_timestamp = int(ttl_time.timestamp())
            
            item = {
                'creator_name': creator_name,
                'processing_date': processing_date,
                'status': 'processing',
                'batch_id': batch_id,
                'content_hash': content_hash,
                'image_count': image_count,
                'processing_config': json.dumps(processing_config),
                'created_at': timestamp,
                'updated_at': timestamp,
                'ttl': ttl_timestamp,
                'lambda_request_id': self.config.LAMBDA_REQUEST_ID or 'local-test',
                'processing_duration_ms': 0,
                'collage_s3_key': ''
            }
            
            # Create record with conditional check to prevent duplicates
            self.table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(creator_name) OR #status <> :processing',
                ExpressionAttributeNames={
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':processing': 'processing'
                }
            )
            
            logger.info(f"Created processing record for creator {creator_name} in batch {batch_id}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"Creator {creator_name} is already being processed")
                return False
            else:
                logger.error(f"Error creating processing record for {creator_name}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error creating processing record for {creator_name}: {e}")
            return False
    
    def update_processing_status(self, creator_name: str, processing_date: str,
                               status: str, collage_s3_key: Optional[str] = None,
                               processing_duration_ms: Optional[int] = None,
                               error_message: Optional[str] = None) -> bool:
        """
        Update processing status for creator
        
        Args:
            creator_name: Name of the creator
            processing_date: Date of processing
            status: New status ('completed', 'failed', 'processing')
            collage_s3_key: S3 key of created collage (if successful)
            processing_duration_ms: Processing duration in milliseconds
            error_message: Error message (if failed)
            
        Returns:
            True if update successful
        """
        try:
            current_time = datetime.utcnow().isoformat()
            
            # Build update expression
            update_expression = 'SET #status = :status, updated_at = :updated_at'
            expression_attribute_names = {'#status': 'status'}
            expression_attribute_values = {
                ':status': status,
                ':updated_at': current_time
            }
            
            if collage_s3_key:
                update_expression += ', collage_s3_key = :s3_key'
                expression_attribute_values[':s3_key'] = collage_s3_key
            
            if processing_duration_ms is not None:
                update_expression += ', processing_duration_ms = :duration'
                expression_attribute_values[':duration'] = processing_duration_ms
            
            if error_message:
                update_expression += ', error_message = :error'
                expression_attribute_values[':error'] = error_message
            
            # Update the record
            self.table.update_item(
                Key={
                    'creator_name': creator_name,
                    'processing_date': processing_date
                },
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
                ConditionExpression='attribute_exists(creator_name)'
            )
            
            logger.info(f"Updated processing status for {creator_name} to {status}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"Processing record not found for creator {creator_name}")
                return False
            else:
                logger.error(f"Error updating processing status for {creator_name}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error updating processing status for {creator_name}: {e}")
            return False
    
    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """
        Get processing status for entire batch
        
        Args:
            batch_id: ID of the batch to check
            
        Returns:
            Dictionary with batch status information
        """
        try:
            # Query by batch_id using GSI
            response = self.table.query(
                IndexName='batch-id-index',
                KeyConditionExpression='batch_id = :batch_id',
                ExpressionAttributeValues={
                    ':batch_id': batch_id
                }
            )
            
            items = response.get('Items', [])
            
            if not items:
                return {
                    'batch_id': batch_id,
                    'total_creators': 0,
                    'status_counts': {},
                    'creators': []
                }
            
            # Analyze status distribution
            status_counts = {}
            creators = []
            
            for item in items:
                status = item.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
                
                creators.append({
                    'creator_name': item.get('creator_name'),
                    'status': status,
                    'created_at': item.get('created_at'),
                    'updated_at': item.get('updated_at'),
                    'collage_s3_key': item.get('collage_s3_key', ''),
                    'processing_duration_ms': item.get('processing_duration_ms', 0)
                })
            
            # Calculate completion percentage
            total_creators = len(items)
            completed_count = status_counts.get('completed', 0)
            completion_percentage = (completed_count / total_creators * 100) if total_creators > 0 else 0
            
            return {
                'batch_id': batch_id,
                'total_creators': total_creators,
                'status_counts': status_counts,
                'completion_percentage': completion_percentage,
                'creators': creators
            }
            
        except Exception as e:
            logger.error(f"Error getting batch status for {batch_id}: {e}")
            return {
                'batch_id': batch_id,
                'error': str(e),
                'total_creators': 0,
                'status_counts': {},
                'creators': []
            }
    
    def get_processing_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get processing statistics for recent days
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary with processing statistics
        """
        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Query recent processing records
            response = self.table.query(
                IndexName='status-date-index',
                KeyConditionExpression='#status = :completed AND processing_date BETWEEN :start_date AND :end_date',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':completed': 'completed',
                    ':start_date': start_date.strftime('%Y-%m-%d'),
                    ':end_date': end_date.strftime('%Y-%m-%d')
                }
            )
            
            items = response.get('Items', [])
            
            # Calculate statistics
            total_processed = len(items)
            total_images = sum(int(item.get('image_count', 0)) for item in items)
            total_duration = sum(int(item.get('processing_duration_ms', 0)) for item in items)
            
            # Group by date
            daily_stats = {}
            for item in items:
                date = item.get('processing_date')
                if date not in daily_stats:
                    daily_stats[date] = {'creators': 0, 'images': 0, 'duration_ms': 0}
                
                daily_stats[date]['creators'] += 1
                daily_stats[date]['images'] += int(item.get('image_count', 0))
                daily_stats[date]['duration_ms'] += int(item.get('processing_duration_ms', 0))
            
            # Calculate averages
            avg_images_per_creator = total_images / total_processed if total_processed > 0 else 0
            avg_duration_per_creator = total_duration / total_processed if total_processed > 0 else 0
            
            return {
                'period_days': days,
                'total_creators_processed': total_processed,
                'total_images_processed': total_images,
                'total_processing_duration_ms': total_duration,
                'average_images_per_creator': round(avg_images_per_creator, 2),
                'average_duration_per_creator_ms': round(avg_duration_per_creator, 2),
                'daily_statistics': daily_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting processing statistics: {e}")
            return {
                'error': str(e),
                'period_days': days,
                'total_creators_processed': 0,
                'total_images_processed': 0
            }
    
    def cleanup_stale_processing_records(self, max_age_minutes: int = 30) -> int:
        """
        Clean up stale processing records (stuck in 'processing' status)
        
        Args:
            max_age_minutes: Maximum age in minutes before considering record stale
            
        Returns:
            Number of records cleaned up
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=max_age_minutes)
            cutoff_timestamp = cutoff_time.isoformat()
            
            # Scan for stale processing records
            response = self.table.scan(
                FilterExpression='#status = :processing AND created_at < :cutoff',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':processing': 'processing',
                    ':cutoff': cutoff_timestamp
                }
            )
            
            stale_items = response.get('Items', [])
            cleanup_count = 0
            
            for item in stale_items:
                creator_name = item['creator_name']
                processing_date = item['processing_date']
                
                # Update status to failed
                success = self.update_processing_status(
                    creator_name=creator_name,
                    processing_date=processing_date,
                    status='failed',
                    error_message=f'Processing timed out after {max_age_minutes} minutes'
                )
                
                if success:
                    cleanup_count += 1
                    logger.info(f"Cleaned up stale processing record for {creator_name}")
            
            logger.info(f"Cleaned up {cleanup_count} stale processing records")
            return cleanup_count
            
        except Exception as e:
            logger.error(f"Error cleaning up stale processing records: {e}")
            return 0
    
    def get_creator_processing_history(self, creator_name: str, 
                                     limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get processing history for specific creator
        
        Args:
            creator_name: Name of the creator
            limit: Maximum number of records to return
            
        Returns:
            List of processing records
        """
        try:
            response = self.table.query(
                KeyConditionExpression='creator_name = :creator_name',
                ExpressionAttributeValues={
                    ':creator_name': creator_name
                },
                ScanIndexForward=False,  # Most recent first
                Limit=limit
            )
            
            items = response.get('Items', [])
            
            # Convert Decimal types to native Python types for JSON serialization
            history = []
            for item in items:
                record = {}
                for key, value in item.items():
                    if isinstance(value, Decimal):
                        record[key] = int(value) if value % 1 == 0 else float(value)
                    else:
                        record[key] = value
                history.append(record)
            
            logger.debug(f"Retrieved {len(history)} processing records for creator {creator_name}")
            return history
            
        except Exception as e:
            logger.error(f"Error getting processing history for creator {creator_name}: {e}")
            return []
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on DynamoDB connection
        
        Returns:
            Dictionary with health check results
        """
        try:
            # Try to describe the table
            table_description = self.table.table_status
            
            # Try a simple query
            response = self.table.scan(Limit=1)
            
            return {
                'healthy': True,
                'table_name': self.table_name,
                'table_status': table_description,
                'connection_test': 'passed'
            }
            
        except Exception as e:
            logger.error(f"DynamoDB health check failed: {e}")
            return {
                'healthy': False,
                'table_name': self.table_name,
                'error': str(e),
                'connection_test': 'failed'
            }
