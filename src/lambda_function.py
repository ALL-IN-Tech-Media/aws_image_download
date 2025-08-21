"""
AWS Lambda handler for TikTok image collage processing
Handles both S3 events and SQS messages for processing CSV files containing image URLs
"""

import json
import logging
import os
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError

from aws_image_processor import AWSImageProcessor
from sqs_processor import SQSProcessor
from s3_utils import S3Utils
from config import Config

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler function
    
    Args:
        event: Lambda event (S3 or SQS)
        context: Lambda context
        
    Returns:
        Dict with processing results
    """
    try:
        logger.info(f"Lambda invocation started. Event: {json.dumps(event, default=str)}")
        
        # Initialize processors
        config = Config()
        image_processor = AWSImageProcessor(config)
        sqs_processor = SQSProcessor(config)
        s3_utils = S3Utils(config)
        
        # Determine event source and process accordingly
        if 'Records' in event:
            if 's3' in event['Records'][0]:
                # S3 event trigger
                logger.info("Processing S3 event")
                return handle_s3_event(event, image_processor, s3_utils, config)
            elif 'eventSource' in event['Records'][0] and event['Records'][0]['eventSource'] == 'aws:sqs':
                # SQS event trigger
                logger.info("Processing SQS event")
                return handle_sqs_event(event, image_processor, sqs_processor, s3_utils, config)
        else:
            # Direct invocation (testing)
            logger.info("Processing direct invocation")
            return handle_direct_invocation(event, image_processor, s3_utils, config)
            
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Unsupported event type',
                'event': event
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Lambda execution failed'
            })
        }

def handle_s3_event(event: Dict[str, Any], image_processor: 'AWSImageProcessor', 
                   s3_utils: 'S3Utils', config: 'Config') -> Dict[str, Any]:
    """
    Handle S3 event (CSV file uploaded)
    
    Args:
        event: S3 event data
        image_processor: Image processing instance
        s3_utils: S3 utilities instance
        config: Configuration instance
        
    Returns:
        Processing results
    """
    results = []
    
    for record in event['Records']:
        try:
            bucket_name = record['s3']['bucket']['name']
            object_key = record['s3']['object']['key']
            
            logger.info(f"Processing S3 object: s3://{bucket_name}/{object_key}")
            
            # Validate that it's a CSV file
            if not object_key.lower().endswith('.csv'):
                logger.warning(f"Skipping non-CSV file: {object_key}")
                continue
            
            # Download and process CSV from S3
            csv_data = s3_utils.download_csv_from_s3(bucket_name, object_key)
            if not csv_data:
                logger.error(f"Failed to download CSV from s3://{bucket_name}/{object_key}")
                continue
            
            # Process the CSV data
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
            
            result = image_processor.process_csv_data(
                csv_data=csv_data,
                output_prefix=f"s3-trigger/{object_key.replace('.csv', '')}/",
                **processing_config
            )
            
            results.append({
                's3_object': f"s3://{bucket_name}/{object_key}",
                'result': result
            })
            
        except Exception as e:
            logger.error(f"Error processing S3 record: {str(e)}", exc_info=True)
            results.append({
                's3_object': f"s3://{bucket_name}/{object_key}",
                'error': str(e)
            })
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Processed {len(results)} S3 objects',
            'results': results
        })
    }

def handle_sqs_event(event: Dict[str, Any], image_processor: 'AWSImageProcessor',
                    sqs_processor: 'SQSProcessor', s3_utils: 'S3Utils', 
                    config: 'Config') -> Dict[str, Any]:
    """
    Handle SQS event (message-based processing)
    
    Args:
        event: SQS event data
        image_processor: Image processing instance
        sqs_processor: SQS processor instance
        s3_utils: S3 utilities instance
        config: Configuration instance
        
    Returns:
        Processing results
    """
    results = []
    
    for record in event['Records']:
        try:
            # Parse SQS message
            message_body = json.loads(record['body'])
            receipt_handle = record['receiptHandle']
            
            logger.info(f"Processing SQS message: {message_body}")
            
            # Process based on message type
            if message_body.get('processing_type') == 'csv_s3':
                # CSV stored in S3
                result = process_csv_from_s3_message(
                    message_body, image_processor, s3_utils
                )
            elif message_body.get('processing_type') == 'csv_data':
                # CSV data in message
                result = process_csv_from_message_data(
                    message_body, image_processor
                )
            else:
                raise ValueError(f"Unsupported processing_type: {message_body.get('processing_type')}")
            
            results.append({
                'message_id': record.get('messageId'),
                'result': result
            })
            
            # Delete message from queue on success
            sqs_processor.delete_message(receipt_handle)
            
        except Exception as e:
            logger.error(f"Error processing SQS message: {str(e)}", exc_info=True)
            results.append({
                'message_id': record.get('messageId'),
                'error': str(e)
            })
            # Message will be retried or sent to DLQ based on queue configuration
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Processed {len(results)} SQS messages',
            'results': results
        })
    }

def process_csv_from_s3_message(message_body: Dict[str, Any], 
                               image_processor: 'AWSImageProcessor',
                               s3_utils: 'S3Utils') -> Dict[str, Any]:
    """
    Process CSV file referenced in SQS message
    
    Args:
        message_body: SQS message content
        image_processor: Image processing instance
        s3_utils: S3 utilities instance
        
    Returns:
        Processing result
    """
    bucket_name = message_body['s3_bucket']
    object_key = message_body['s3_key']
    processing_config = message_body.get('processing_config', {})
    output_prefix = message_body.get('output_prefix', 'sqs-trigger/')
    
    # Download CSV from S3
    csv_data = s3_utils.download_csv_from_s3(bucket_name, object_key)
    if not csv_data:
        raise ValueError(f"Failed to download CSV from s3://{bucket_name}/{object_key}")
    
    # Set default processing configuration
    config_defaults = {
        'group_by_creator': True,
        'rows': 5,
        'cols': 7,
        'max_images_per_creator': 35,
        'quality': 95,
        'max_workers': 8,
        'timeout': 30,
        'max_retries': 3
    }
    config_defaults.update(processing_config)
    
    # Process the CSV data
    return image_processor.process_csv_data(
        csv_data=csv_data,
        output_prefix=output_prefix,
        **config_defaults
    )

def process_csv_from_message_data(message_body: Dict[str, Any],
                                 image_processor: 'AWSImageProcessor') -> Dict[str, Any]:
    """
    Process CSV data included in SQS message
    
    Args:
        message_body: SQS message content
        image_processor: Image processing instance
        
    Returns:
        Processing result
    """
    csv_data = message_body['csv_data']
    processing_config = message_body.get('processing_config', {})
    output_prefix = message_body.get('output_prefix', 'sqs-data/')
    
    # Set default processing configuration
    config_defaults = {
        'group_by_creator': True,
        'rows': 5,
        'cols': 7,
        'max_images_per_creator': 35,
        'quality': 95,
        'max_workers': 8,
        'timeout': 30,
        'max_retries': 3
    }
    config_defaults.update(processing_config)
    
    # Process the CSV data
    return image_processor.process_csv_data(
        csv_data=csv_data,
        output_prefix=output_prefix,
        **config_defaults
    )

def handle_direct_invocation(event: Dict[str, Any], image_processor: 'AWSImageProcessor',
                           s3_utils: 'S3Utils', config: 'Config') -> Dict[str, Any]:
    """
    Handle direct Lambda invocation (for testing)
    
    Args:
        event: Direct invocation event
        image_processor: Image processing instance
        s3_utils: S3 utilities instance
        config: Configuration instance
        
    Returns:
        Processing results
    """
    if 'test_csv_data' in event:
        # Test with provided CSV data
        result = image_processor.process_csv_data(
            csv_data=event['test_csv_data'],
            output_prefix='direct-test/',
            group_by_creator=True,
            rows=5,
            cols=7,
            max_images_per_creator=35,
            quality=95
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Direct invocation test completed',
                'result': result
            })
        }
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Direct invocation requires test_csv_data parameter'
            })
        }
