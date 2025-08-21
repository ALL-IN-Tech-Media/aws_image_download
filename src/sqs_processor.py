"""
SQS message processor for AWS Lambda image processing
Handles SQS message operations including receiving, processing, and deleting messages
"""

import boto3
import json
import logging
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError

from config import Config

logger = logging.getLogger(__name__)

class SQSProcessor:
    """SQS processor class for message operations"""
    
    def __init__(self, config: 'Config'):
        """
        Initialize SQS processor
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.sqs_client = boto3.client('sqs')
        
    def send_message(self, message_body: Dict[str, Any], 
                    queue_url: Optional[str] = None,
                    delay_seconds: int = 0,
                    message_attributes: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Send message to SQS queue
        
        Args:
            message_body: Message content as dictionary
            queue_url: SQS queue URL (uses default if not specified)
            delay_seconds: Delay before message becomes available
            message_attributes: Optional message attributes
            
        Returns:
            Message ID or None if failed
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            send_args = {
                'QueueUrl': queue_url,
                'MessageBody': json.dumps(message_body)
            }
            
            if delay_seconds > 0:
                send_args['DelaySeconds'] = delay_seconds
            
            if message_attributes:
                send_args['MessageAttributes'] = message_attributes
            
            logger.info(f"Sending message to SQS queue: {queue_url}")
            
            response = self.sqs_client.send_message(**send_args)
            
            message_id = response['MessageId']
            logger.info(f"Successfully sent message: {message_id}")
            
            return message_id
            
        except ClientError as e:
            logger.error(f"Error sending SQS message: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error sending SQS message: {e}")
            return None
    
    def send_message_batch(self, messages: List[Dict[str, Any]], 
                          queue_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Send multiple messages to SQS queue in batch
        
        Args:
            messages: List of message dictionaries
            queue_url: SQS queue URL (uses default if not specified)
            
        Returns:
            Dictionary with successful and failed messages
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            if not messages:
                logger.warning("No messages to send")
                return {'successful': [], 'failed': []}
            
            # SQS batch limit is 10 messages
            batch_size = 10
            all_successful = []
            all_failed = []
            
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i + batch_size]
                
                # Prepare batch entries
                entries = []
                for j, message in enumerate(batch):
                    entry = {
                        'Id': f"msg_{i + j}",
                        'MessageBody': json.dumps(message)
                    }
                    entries.append(entry)
                
                logger.info(f"Sending batch of {len(entries)} messages to SQS queue")
                
                response = self.sqs_client.send_message_batch(
                    QueueUrl=queue_url,
                    Entries=entries
                )
                
                # Process successful messages
                if 'Successful' in response:
                    all_successful.extend(response['Successful'])
                    logger.info(f"Successfully sent {len(response['Successful'])} messages")
                
                # Process failed messages
                if 'Failed' in response:
                    all_failed.extend(response['Failed'])
                    logger.error(f"Failed to send {len(response['Failed'])} messages")
                    for failed_msg in response['Failed']:
                        logger.error(f"Failed message ID {failed_msg['Id']}: {failed_msg['Code']} - {failed_msg['Message']}")
            
            return {
                'successful': all_successful,
                'failed': all_failed,
                'total_sent': len(all_successful),
                'total_failed': len(all_failed)
            }
            
        except ClientError as e:
            logger.error(f"Error sending SQS message batch: {e}")
            return {'successful': [], 'failed': messages, 'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error sending SQS message batch: {e}")
            return {'successful': [], 'failed': messages, 'error': str(e)}
    
    def receive_messages(self, queue_url: Optional[str] = None,
                        max_messages: int = 10,
                        wait_time_seconds: int = 20,
                        visibility_timeout: int = 300) -> List[Dict[str, Any]]:
        """
        Receive messages from SQS queue
        
        Args:
            queue_url: SQS queue URL (uses default if not specified)
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time
            visibility_timeout: Message visibility timeout
            
        Returns:
            List of received messages
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            logger.info(f"Receiving messages from SQS queue: {queue_url}")
            
            response = self.sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=min(max_messages, 10),  # SQS limit is 10
                WaitTimeSeconds=wait_time_seconds,
                VisibilityTimeoutSeconds=visibility_timeout,
                MessageAttributeNames=['All']
            )
            
            messages = response.get('Messages', [])
            logger.info(f"Received {len(messages)} messages from SQS")
            
            return messages
            
        except ClientError as e:
            logger.error(f"Error receiving SQS messages: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error receiving SQS messages: {e}")
            return []
    
    def delete_message(self, receipt_handle: str, queue_url: Optional[str] = None) -> bool:
        """
        Delete message from SQS queue
        
        Args:
            receipt_handle: Message receipt handle
            queue_url: SQS queue URL (uses default if not specified)
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            self.sqs_client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            
            logger.debug("Successfully deleted SQS message")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting SQS message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting SQS message: {e}")
            return False
    
    def delete_message_batch(self, receipt_handles: List[str], 
                           queue_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Delete multiple messages from SQS queue in batch
        
        Args:
            receipt_handles: List of message receipt handles
            queue_url: SQS queue URL (uses default if not specified)
            
        Returns:
            Dictionary with successful and failed deletions
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            if not receipt_handles:
                logger.warning("No receipt handles to delete")
                return {'successful': [], 'failed': []}
            
            # SQS batch limit is 10 messages
            batch_size = 10
            all_successful = []
            all_failed = []
            
            for i in range(0, len(receipt_handles), batch_size):
                batch = receipt_handles[i:i + batch_size]
                
                # Prepare batch entries
                entries = []
                for j, receipt_handle in enumerate(batch):
                    entry = {
                        'Id': f"del_{i + j}",
                        'ReceiptHandle': receipt_handle
                    }
                    entries.append(entry)
                
                logger.info(f"Deleting batch of {len(entries)} messages from SQS queue")
                
                response = self.sqs_client.delete_message_batch(
                    QueueUrl=queue_url,
                    Entries=entries
                )
                
                # Process successful deletions
                if 'Successful' in response:
                    all_successful.extend(response['Successful'])
                    logger.info(f"Successfully deleted {len(response['Successful'])} messages")
                
                # Process failed deletions
                if 'Failed' in response:
                    all_failed.extend(response['Failed'])
                    logger.error(f"Failed to delete {len(response['Failed'])} messages")
                    for failed_del in response['Failed']:
                        logger.error(f"Failed deletion ID {failed_del['Id']}: {failed_del['Code']} - {failed_del['Message']}")
            
            return {
                'successful': all_successful,
                'failed': all_failed,
                'total_deleted': len(all_successful),
                'total_failed': len(all_failed)
            }
            
        except ClientError as e:
            logger.error(f"Error deleting SQS message batch: {e}")
            return {'successful': [], 'failed': receipt_handles, 'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error deleting SQS message batch: {e}")
            return {'successful': [], 'failed': receipt_handles, 'error': str(e)}
    
    def change_message_visibility(self, receipt_handle: str, visibility_timeout: int,
                                queue_url: Optional[str] = None) -> bool:
        """
        Change message visibility timeout
        
        Args:
            receipt_handle: Message receipt handle
            visibility_timeout: New visibility timeout in seconds
            queue_url: SQS queue URL (uses default if not specified)
            
        Returns:
            True if change successful, False otherwise
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            self.sqs_client.change_message_visibility(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_timeout
            )
            
            logger.debug(f"Changed message visibility timeout to {visibility_timeout} seconds")
            return True
            
        except ClientError as e:
            logger.error(f"Error changing message visibility: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error changing message visibility: {e}")
            return False
    
    def get_queue_attributes(self, queue_url: Optional[str] = None,
                           attribute_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get SQS queue attributes
        
        Args:
            queue_url: SQS queue URL (uses default if not specified)
            attribute_names: List of attribute names to retrieve
            
        Returns:
            Dictionary of queue attributes
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            if not attribute_names:
                attribute_names = ['All']
            
            response = self.sqs_client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=attribute_names
            )
            
            attributes = response.get('Attributes', {})
            logger.debug(f"Retrieved {len(attributes)} queue attributes")
            
            return attributes
            
        except ClientError as e:
            logger.error(f"Error getting queue attributes: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error getting queue attributes: {e}")
            return {}
    
    def purge_queue(self, queue_url: Optional[str] = None) -> bool:
        """
        Purge all messages from SQS queue
        
        Args:
            queue_url: SQS queue URL (uses default if not specified)
            
        Returns:
            True if purge successful, False otherwise
        """
        try:
            if not queue_url:
                queue_url = self.config.SQS_QUEUE_URL
            
            logger.warning(f"Purging all messages from SQS queue: {queue_url}")
            
            self.sqs_client.purge_queue(QueueUrl=queue_url)
            
            logger.info("Successfully purged SQS queue")
            return True
            
        except ClientError as e:
            logger.error(f"Error purging SQS queue: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error purging SQS queue: {e}")
            return False
    
    def create_csv_processing_message(self, csv_s3_bucket: str, csv_s3_key: str,
                                    processing_config: Optional[Dict[str, Any]] = None,
                                    output_prefix: str = "") -> Dict[str, Any]:
        """
        Create SQS message for CSV processing from S3
        
        Args:
            csv_s3_bucket: S3 bucket containing CSV file
            csv_s3_key: S3 key of CSV file
            processing_config: Processing configuration parameters
            output_prefix: Output prefix for generated files
            
        Returns:
            SQS message dictionary
        """
        if not processing_config:
            processing_config = {
                'group_by_creator': True,
                'rows': 5,
                'cols': 7,
                'max_images_per_creator': 35,
                'quality': 95,
                'max_workers': 8,
                'timeout': 30,
                'max_retries': 3
            }
        
        message = {
            'processing_type': 'csv_s3',
            's3_bucket': csv_s3_bucket,
            's3_key': csv_s3_key,
            'processing_config': processing_config,
            'output_prefix': output_prefix,
            'timestamp': str(datetime.datetime.utcnow()),
            'source': 'local_upload'
        }
        
        return message
    
    def create_csv_data_message(self, csv_data: str,
                              processing_config: Optional[Dict[str, Any]] = None,
                              output_prefix: str = "") -> Dict[str, Any]:
        """
        Create SQS message for CSV processing from data
        
        Args:
            csv_data: CSV data as string
            processing_config: Processing configuration parameters
            output_prefix: Output prefix for generated files
            
        Returns:
            SQS message dictionary
        """
        if not processing_config:
            processing_config = {
                'group_by_creator': True,
                'rows': 5,
                'cols': 7,
                'max_images_per_creator': 35,
                'quality': 95,
                'max_workers': 8,
                'timeout': 30,
                'max_retries': 3
            }
        
        message = {
            'processing_type': 'csv_data',
            'csv_data': csv_data,
            'processing_config': processing_config,
            'output_prefix': output_prefix,
            'timestamp': str(datetime.datetime.utcnow()),
            'source': 'direct_data'
        }
        
        return message
    
    def send_csv_processing_request(self, csv_s3_bucket: str, csv_s3_key: str,
                                  processing_config: Optional[Dict[str, Any]] = None,
                                  output_prefix: str = "",
                                  queue_url: Optional[str] = None) -> Optional[str]:
        """
        Send CSV processing request to SQS queue
        
        Args:
            csv_s3_bucket: S3 bucket containing CSV file
            csv_s3_key: S3 key of CSV file
            processing_config: Processing configuration parameters
            output_prefix: Output prefix for generated files
            queue_url: SQS queue URL (uses default if not specified)
            
        Returns:
            Message ID or None if failed
        """
        message = self.create_csv_processing_message(
            csv_s3_bucket, csv_s3_key, processing_config, output_prefix
        )
        
        return self.send_message(message, queue_url)
    
    def get_dlq_messages(self, dlq_url: Optional[str] = None,
                        max_messages: int = 10) -> List[Dict[str, Any]]:
        """
        Get messages from Dead Letter Queue for analysis
        
        Args:
            dlq_url: DLQ URL (uses default if not specified)
            max_messages: Maximum number of messages to retrieve
            
        Returns:
            List of DLQ messages
        """
        try:
            if not dlq_url:
                dlq_url = self.config.SQS_DLQ_URL
            
            if not dlq_url:
                logger.error("No DLQ URL configured")
                return []
            
            logger.info(f"Retrieving messages from DLQ: {dlq_url}")
            
            response = self.sqs_client.receive_message(
                QueueUrl=dlq_url,
                MaxNumberOfMessages=min(max_messages, 10),
                MessageAttributeNames=['All']
            )
            
            messages = response.get('Messages', [])
            logger.info(f"Retrieved {len(messages)} messages from DLQ")
            
            return messages
            
        except ClientError as e:
            logger.error(f"Error retrieving DLQ messages: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error retrieving DLQ messages: {e}")
            return []

# Import datetime at the top if not already imported
import datetime
