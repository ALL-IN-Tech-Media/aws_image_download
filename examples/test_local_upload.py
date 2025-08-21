#!/usr/bin/env python3
"""
Local testing script for AWS image processing pipeline
Tests SQS message sending and S3 file uploads
"""

import boto3
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

def load_environment():
    """Load environment variables from .env file if it exists"""
    env_file = '.env'
    if os.path.exists(env_file):
        print(f"Loading environment from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    else:
        print("No .env file found. Using existing environment variables.")

def get_aws_clients():
    """Initialize AWS clients"""
    try:
        s3_client = boto3.client('s3')
        sqs_client = boto3.client('sqs')
        
        # Test AWS credentials
        sts_client = boto3.client('sts')
        identity = sts_client.get_caller_identity()
        print(f"AWS Account: {identity['Account']}")
        print(f"AWS User/Role: {identity['Arn']}")
        
        return s3_client, sqs_client
    except Exception as e:
        print(f"Error initializing AWS clients: {e}")
        print("Please ensure AWS credentials are configured:")
        print("  aws configure")
        sys.exit(1)

def upload_csv_to_s3(s3_client, csv_file_path: str, bucket_name: str, s3_key: str) -> bool:
    """Upload CSV file to S3"""
    try:
        if not os.path.exists(csv_file_path):
            print(f"Error: CSV file not found: {csv_file_path}")
            return False
        
        print(f"Uploading {csv_file_path} to s3://{bucket_name}/{s3_key}")
        
        with open(csv_file_path, 'rb') as f:
            s3_client.upload_fileobj(f, bucket_name, s3_key)
        
        print(f"✓ Successfully uploaded to s3://{bucket_name}/{s3_key}")
        return True
        
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False

def send_sqs_message(sqs_client, queue_url: str, message_body: Dict[str, Any]) -> bool:
    """Send message to SQS queue"""
    try:
        print(f"Sending message to SQS queue: {queue_url}")
        print(f"Message: {json.dumps(message_body, indent=2)}")
        
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body)
        )
        
        message_id = response['MessageId']
        print(f"✓ Message sent successfully. MessageId: {message_id}")
        return True
        
    except Exception as e:
        print(f"Error sending SQS message: {e}")
        return False

def test_s3_trigger(s3_client, csv_file_path: str, input_bucket: str):
    """Test S3 automatic trigger by uploading CSV to csv-files/ folder"""
    print("\n" + "="*50)
    print("TEST 1: S3 Automatic Trigger")
    print("="*50)
    
    # Generate S3 key with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(csv_file_path)
    name_without_ext = os.path.splitext(filename)[0]
    s3_key = f"csv-files/{datetime.now().strftime('%Y/%m/%d')}/{name_without_ext}_test_{timestamp}.csv"
    
    success = upload_csv_to_s3(s3_client, csv_file_path, input_bucket, s3_key)
    
    if success:
        print(f"✓ S3 trigger test completed")
        print(f"  - Lambda should automatically process this file")
        print(f"  - Check CloudWatch logs: /aws/lambda/image-collage-processor")
        print(f"  - Results will appear in: s3://{os.environ.get('OUTPUT_BUCKET', 'tiktok-image-output')}/collages/")
    else:
        print("✗ S3 trigger test failed")

def test_sqs_trigger(s3_client, sqs_client, csv_file_path: str, input_bucket: str, queue_url: str):
    """Test SQS trigger by uploading CSV and sending SQS message"""
    print("\n" + "="*50)
    print("TEST 2: SQS Manual Trigger")
    print("="*50)
    
    # Upload CSV to manual-uploads folder (won't auto-trigger)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(csv_file_path)
    name_without_ext = os.path.splitext(filename)[0]
    s3_key = f"manual-uploads/{name_without_ext}_sqs_test_{timestamp}.csv"
    
    # Upload CSV
    upload_success = upload_csv_to_s3(s3_client, csv_file_path, input_bucket, s3_key)
    
    if not upload_success:
        print("✗ SQS trigger test failed - CSV upload failed")
        return
    
    # Create SQS message
    message_body = {
        "processing_type": "csv_s3",
        "s3_bucket": input_bucket,
        "s3_key": s3_key,
        "processing_config": {
            "group_by_creator": True,
            "rows": 5,
            "cols": 7,
            "max_images_per_creator": 35,
            "quality": 95,
            "max_workers": 8,
            "timeout": 30,
            "max_retries": 3
        },
        "output_prefix": f"sqs-test/{timestamp}/",
        "timestamp": datetime.now().isoformat(),
        "source": "local_test_script"
    }
    
    # Send SQS message
    sqs_success = send_sqs_message(sqs_client, queue_url, message_body)
    
    if sqs_success:
        print(f"✓ SQS trigger test completed")
        print(f"  - Lambda should process this file via SQS trigger")
        print(f"  - Check SQS queue for message processing")
        print(f"  - Results will appear in: s3://{os.environ.get('OUTPUT_BUCKET', 'tiktok-image-output')}/collages/sqs-test/{timestamp}/")
    else:
        print("✗ SQS trigger test failed")

def test_direct_csv_data(sqs_client, csv_file_path: str, queue_url: str):
    """Test sending CSV data directly in SQS message"""
    print("\n" + "="*50)
    print("TEST 3: Direct CSV Data in SQS")
    print("="*50)
    
    try:
        # Read CSV content
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()
        
        # Limit CSV size for SQS (256KB limit)
        if len(csv_content) > 200000:  # 200KB safety margin
            print("Warning: CSV file is large. Taking first 50 lines for test...")
            lines = csv_content.split('\n')
            csv_content = '\n'.join(lines[:51])  # Header + 50 data lines
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create SQS message with CSV data
        message_body = {
            "processing_type": "csv_data",
            "csv_data": csv_content,
            "processing_config": {
                "group_by_creator": True,
                "rows": 3,  # Smaller grid for test
                "cols": 3,
                "max_images_per_creator": 9,
                "quality": 90,
                "max_workers": 4,
                "timeout": 30,
                "max_retries": 2
            },
            "output_prefix": f"csv-data-test/{timestamp}/",
            "timestamp": datetime.now().isoformat(),
            "source": "local_test_script_direct_data"
        }
        
        # Send SQS message
        sqs_success = send_sqs_message(sqs_client, queue_url, message_body)
        
        if sqs_success:
            print(f"✓ Direct CSV data test completed")
            print(f"  - Lambda should process CSV data from SQS message")
            print(f"  - Results will appear in: s3://{os.environ.get('OUTPUT_BUCKET', 'tiktok-image-output')}/collages/csv-data-test/{timestamp}/")
        else:
            print("✗ Direct CSV data test failed")
            
    except Exception as e:
        print(f"Error in direct CSV data test: {e}")

def check_resources(s3_client, sqs_client):
    """Check if required AWS resources exist"""
    print("\n" + "="*50)
    print("CHECKING AWS RESOURCES")
    print("="*50)
    
    # Check environment variables
    required_vars = ['INPUT_BUCKET', 'OUTPUT_BUCKET', 'SQS_QUEUE_URL']
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"Error: Missing environment variables: {missing_vars}")
        print("Please run ./setup_infrastructure.sh first to create resources")
        return False
    
    # Check S3 buckets
    input_bucket = os.environ['INPUT_BUCKET']
    output_bucket = os.environ['OUTPUT_BUCKET']
    
    try:
        s3_client.head_bucket(Bucket=input_bucket)
        print(f"✓ Input bucket exists: {input_bucket}")
    except Exception as e:
        print(f"✗ Input bucket not accessible: {input_bucket} - {e}")
        return False
    
    try:
        s3_client.head_bucket(Bucket=output_bucket)
        print(f"✓ Output bucket exists: {output_bucket}")
    except Exception as e:
        print(f"✗ Output bucket not accessible: {output_bucket} - {e}")
        return False
    
    # Check SQS queue
    queue_url = os.environ['SQS_QUEUE_URL']
    try:
        sqs_client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=['QueueArn'])
        print(f"✓ SQS queue exists: {queue_url}")
    except Exception as e:
        print(f"✗ SQS queue not accessible: {queue_url} - {e}")
        return False
    
    return True

def main():
    print("TikTok Image Processing - Local Test Script")
    print("=" * 50)
    
    # Load environment
    load_environment()
    
    # Initialize AWS clients
    s3_client, sqs_client = get_aws_clients()
    
    # Check resources
    if not check_resources(s3_client, sqs_client):
        print("\nPlease run ./setup_infrastructure.sh to create required resources")
        sys.exit(1)
    
    # Find CSV file to test with
    csv_file = None
    possible_files = [
        'cover_urls_20250818_235148.csv',
        'cover_urls_20250819_032357.csv'
    ]
    
    for filename in possible_files:
        if os.path.exists(filename):
            csv_file = filename
            break
    
    if not csv_file:
        print(f"\nError: No test CSV file found.")
        print(f"Please ensure one of these files exists in the current directory:")
        for filename in possible_files:
            print(f"  - {filename}")
        print("\nOr run get_urls.py to generate a new CSV file")
        sys.exit(1)
    
    print(f"\nUsing CSV file: {csv_file}")
    
    # Get configuration
    input_bucket = os.environ['INPUT_BUCKET']
    queue_url = os.environ['SQS_QUEUE_URL']
    
    # Run tests
    try:
        # Test 1: S3 automatic trigger
        test_s3_trigger(s3_client, csv_file, input_bucket)
        
        # Test 2: SQS manual trigger
        test_sqs_trigger(s3_client, sqs_client, csv_file, input_bucket, queue_url)
        
        # Test 3: Direct CSV data
        test_direct_csv_data(sqs_client, csv_file, queue_url)
        
        print("\n" + "="*50)
        print("ALL TESTS COMPLETED")
        print("="*50)
        print("\nNext steps:")
        print("1. Check CloudWatch logs: aws logs tail /aws/lambda/image-collage-processor --follow")
        print("2. Monitor SQS queue: aws sqs get-queue-attributes --queue-url", queue_url)
        print("3. Check output bucket: aws s3 ls s3://" + os.environ.get('OUTPUT_BUCKET', 'tiktok-image-output') + "/collages/ --recursive")
        print("4. View processing results in AWS S3 Console")
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")

if __name__ == "__main__":
    main()
