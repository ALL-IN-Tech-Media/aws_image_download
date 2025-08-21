# SQS Pipeline - Detailed Technical Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture Components](#architecture-components)
3. [Message Types and Structure](#message-types-and-structure)
4. [Processing Workflow](#processing-workflow)
5. [Lambda Integration](#lambda-integration)
6. [Error Handling and Retry Logic](#error-handling-and-retry-logic)
7. [Monitoring and Observability](#monitoring-and-observability)
8. [Usage Examples](#usage-examples)
9. [Performance and Optimization](#performance-and-optimization)
10. [Troubleshooting](#troubleshooting)

## Overview

The SQS (Simple Queue Service) pipeline provides a robust, scalable message-driven architecture for processing TikTok image URLs and generating collages. Unlike the direct S3 trigger approach, the SQS pipeline offers controlled processing, batch operations, retry mechanisms, and better error handling for large-scale operations.

### Key Benefits
- **Controlled Processing**: Process on-demand rather than immediate S3 triggers
- **Batch Operations**: Handle large CSV files through intelligent batching
- **Retry Logic**: Automatic retry with exponential backoff for failed operations
- **Dead Letter Queue**: Capture and analyze failed messages
- **Scalability**: Support for concurrent Lambda executions (up to 50)
- **Cost Optimization**: Pay-per-use with efficient resource utilization

## Architecture Components

### Core Infrastructure
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CSV Upload    │    │   SQS Message    │    │ Lambda Function │
│   (Local/S3)    │───▶│     Queue        │───▶│   Processing    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │  Dead Letter     │    │   S3 Output     │
                       │     Queue        │    │    Bucket       │
                       └──────────────────┘    └─────────────────┘
```

### AWS Services Used
1. **Amazon SQS**: Message queuing and management
2. **AWS Lambda**: Serverless processing engine
3. **Amazon S3**: Input CSV storage and output collage storage
4. **CloudWatch**: Logging, monitoring, and alerting
5. **IAM**: Access control and permissions

### Queue Configuration
- **Main Queue**: `tiktok-image-processing-queue`
  - Message Retention: 14 days
  - Visibility Timeout: 15 minutes (matches Lambda timeout)
  - Long Polling: 20 seconds
  - Max Receive Count: 3 (before moving to DLQ)

- **Dead Letter Queue**: `tiktok-image-processing-dlq`
  - Message Retention: 14 days
  - Used for failed message analysis and manual reprocessing

## Message Types and Structure

The SQS pipeline supports two distinct message types for different processing scenarios:

### Type 1: CSV from S3 Reference (`csv_s3`)

**Use Case**: Large CSV files stored in S3, batch processing
**Message Structure**:
```json
{
  "processing_type": "csv_s3",
  "s3_bucket": "tiktok-image-input",
  "s3_key": "csv-files/cover_urls_20250822_010628.csv",
  "processing_config": {
    "group_by_creator": true,
    "rows": 5,
    "cols": 7,
    "max_images_per_creator": 35,
    "quality": 95,
    "max_workers": 8,
    "timeout": 30,
    "max_retries": 3
  },
  "output_prefix": "collages/2025/08/22/sqs-trigger/batch-001/",
  "timestamp": "2025-08-22T10:30:00.000Z",
  "source": "parallel_processor"
}
```

**Field Descriptions**:
- `processing_type`: Always "csv_s3" for S3-referenced CSV files
- `s3_bucket`: S3 bucket containing the CSV file
- `s3_key`: Full S3 key path to the CSV file
- `processing_config`: Processing parameters (optional, defaults applied if missing)
- `output_prefix`: S3 path prefix for generated collages
- `timestamp`: Message creation timestamp (UTC)
- `source`: Identifies the source that created the message

### Type 2: Embedded CSV Data (`csv_data`)

**Use Case**: Small CSV datasets, direct data processing
**Message Structure**:
```json
{
  "processing_type": "csv_data",
  "csv_data": "creator_name,cover_url,created_at\nuser1,https://example.com/image1.jpg,2025-08-22\nuser2,https://example.com/image2.jpg,2025-08-22",
  "processing_config": {
    "group_by_creator": true,
    "rows": 5,
    "cols": 7,
    "quality": 95,
    "max_workers": 8,
    "timeout": 30,
    "max_retries": 3
  },
  "output_prefix": "collages/2025/08/22/sqs-trigger/direct-data/",
  "timestamp": "2025-08-22T10:30:00.000Z",
  "source": "direct_upload"
}
```

**Field Descriptions**:
- `processing_type`: Always "csv_data" for embedded CSV data
- `csv_data`: Complete CSV content as string (header + data rows)
- `processing_config`: Processing parameters (same as csv_s3 type)
- `output_prefix`: S3 path prefix for generated collages
- `timestamp`: Message creation timestamp (UTC)
- `source`: Identifies the source that created the message

### Processing Configuration Parameters

```json
{
  "group_by_creator": true,           // Group images by creator name
  "rows": 5,                         // Collage grid rows
  "cols": 7,                         // Collage grid columns  
  "max_images_per_creator": 35,      // Maximum images per collage (rows × cols)
  "quality": 95,                     // JPEG quality (1-100)
  "max_workers": 8,                  // Concurrent download threads
  "timeout": 30,                     // HTTP request timeout (seconds)
  "max_retries": 3                   // Retry attempts for failed downloads
}
```

## Processing Workflow

### Step 1: Message Creation and Sending

**Automatic Creation (via SQSProcessor)**:
```python
from sqs_processor import SQSProcessor
from config import Config

config = Config()
sqs_processor = SQSProcessor(config)

# For S3-referenced CSV
message_id = sqs_processor.send_csv_processing_request(
    csv_s3_bucket="tiktok-image-input",
    csv_s3_key="csv-files/cover_urls_20250822_010628.csv",
    processing_config={
        "rows": 5,
        "cols": 7,
        "quality": 95
    },
    output_prefix="collages/2025/08/22/sqs-trigger/batch-001/"
)
```

**Manual Message Creation**:
```python
import boto3
import json

sqs = boto3.client('sqs')
queue_url = "https://sqs.us-east-2.amazonaws.com/624433616538/tiktok-image-processing-queue"

message = {
    "processing_type": "csv_s3",
    "s3_bucket": "tiktok-image-input",
    "s3_key": "csv-files/your-file.csv",
    "processing_config": {"rows": 5, "cols": 7},
    "output_prefix": "collages/2025/08/22/sqs-trigger/custom-batch/"
}

response = sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(message)
)
```

### Step 2: Lambda Polling and Message Reception

**Automatic Polling**:
- Lambda automatically polls the SQS queue using long polling (20 seconds)
- Up to 10 messages can be retrieved per poll
- Lambda can process multiple messages concurrently (up to 50 concurrent executions)

**Message Processing Flow**:
```python
def lambda_handler(event, context):
    # 1. Detect event source (SQS vs S3)
    if 'Records' in event and event['Records'][0]['eventSource'] == 'aws:sqs':
        return handle_sqs_event(event, ...)
    
def handle_sqs_event(event, ...):
    for record in event['Records']:
        # 2. Parse message body
        message_body = json.loads(record['body'])
        receipt_handle = record['receiptHandle']
        
        # 3. Route based on processing type
        if message_body.get('processing_type') == 'csv_s3':
            result = process_csv_from_s3_message(message_body, ...)
        elif message_body.get('processing_type') == 'csv_data':
            result = process_csv_from_message_data(message_body, ...)
        
        # 4. Delete message on success
        sqs_processor.delete_message(receipt_handle)
```

### Step 3: CSV Data Processing

**For `csv_s3` Messages**:
1. **Download CSV**: Retrieve CSV file from specified S3 location
2. **Parse Data**: Convert CSV to structured data with validation
3. **Group by Creator**: Organize URLs by creator name (if configured)
4. **Validate URLs**: Check URL format and accessibility

**For `csv_data` Messages**:
1. **Parse Embedded Data**: Extract CSV content directly from message
2. **Data Validation**: Validate CSV format and required columns
3. **Group by Creator**: Organize URLs by creator name (if configured)
4. **Validate URLs**: Check URL format and accessibility

### Step 4: Image Download and Processing

**Concurrent Download Process**:
```python
def download_images_batch(self, urls, max_workers=8, timeout=30, max_retries=3):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_url = {
            executor.submit(self.download_image_from_url, url, timeout, max_retries): url 
            for url in urls
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                image = future.result()
                if image:
                    images.append(image)
            except Exception as e:
                logger.error(f"Failed to download {url}: {e}")
```

**Image Validation**:
- Content-Type verification (image/jpeg, image/png, etc.)
- Minimum size validation (50x50 pixels)
- Format conversion (RGBA → RGB for JPEG compatibility)
- Memory usage monitoring

### Step 5: Collage Creation

**Grid Layout Calculation**:
```python
def create_image_collage_s3(self, urls, s3_key, rows=5, cols=7, quality=95):
    # 1. Calculate dimensions
    total_images = min(len(urls), rows * cols)
    
    # 2. Download images concurrently
    images = self.download_images_batch(urls[:total_images], ...)
    
    # 3. Calculate canvas size
    canvas_width = cols * 200  # 200px per image
    canvas_height = rows * 200
    
    # 4. Create collage canvas
    collage = Image.new('RGB', (canvas_width, canvas_height), 'white')
    
    # 5. Place images in grid
    for i, img in enumerate(images):
        row = i // cols
        col = i % cols
        x = col * 200
        y = row * 200
        
        # Resize and paste image
        img_resized = img.resize((200, 200), Image.Resampling.LANCZOS)
        collage.paste(img_resized, (x, y))
    
    # 6. Upload to S3
    return self.s3_utils.upload_image_to_s3(collage, s3_key, quality)
```

### Step 6: S3 Upload and Result Generation

**Output Structure**:
```
tiktok-image-output/
└── collages/
    └── 2025/
        └── 08/
            └── 22/
                └── sqs-trigger/
                    └── batch-001/
                        ├── creator1_collage_20250822_103045.jpg
                        ├── creator2_collage_20250822_103046.jpg
                        └── creator3_collage_20250822_103047.jpg
```

**Result Metadata**:
```json
{
  "processing_summary": {
    "total_creators": 150,
    "collages_created": 148,
    "failed_creators": 2,
    "total_images_processed": 5180,
    "processing_duration": "00:12:34",
    "memory_peak": "2.1 GB"
  },
  "collages_created": [
    {
      "creator": "creator1",
      "s3_key": "collages/2025/08/22/sqs-trigger/batch-001/creator1_collage_20250822_103045.jpg",
      "s3_url": "https://s3.amazonaws.com/...",
      "image_count": 35
    }
  ],
  "failed_creators": ["creator_with_no_valid_images", "creator_with_network_errors"]
}
```

## Lambda Integration

### Lambda Function Configuration
```yaml
Function Name: image-collage-processor
Runtime: Python 3.11
Memory: 3008 MB (maximum for CPU optimization)
Timeout: 15 minutes
Environment Variables:
  - INPUT_BUCKET: tiktok-image-input
  - OUTPUT_BUCKET: tiktok-image-output
  - TEMP_BUCKET: tiktok-image-temp
  - SQS_QUEUE_URL: https://sqs.us-east-2.amazonaws.com/.../tiktok-image-processing-queue
  - SQS_DLQ_URL: https://sqs.us-east-2.amazonaws.com/.../tiktok-image-processing-dlq
```

### Event Source Mapping
```yaml
SQS Trigger Configuration:
  - Event Source: SQS Queue
  - Batch Size: 10 (maximum messages per invocation)
  - Maximum Batching Window: 5 seconds
  - Concurrent Executions: 50
  - Retry Attempts: 3
  - Dead Letter Queue: Enabled
```

### IAM Permissions Required
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:*:*:tiktok-image-processing-queue"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::tiktok-image-input/*",
        "arn:aws:s3:::tiktok-image-output/*",
        "arn:aws:s3:::tiktok-image-temp/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

## Error Handling and Retry Logic

### Multi-Level Retry Strategy

#### 1. HTTP Request Level (Image Downloads)
```python
def download_image_from_url(self, url, timeout=30, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout, headers=self.headers)
            if response.status_code == 200:
                return Image.open(io.BytesIO(response.content))
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to download {url} after {max_retries} attempts: {e}")
                return None
            
            # Exponential backoff
            sleep_time = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(sleep_time)
```

#### 2. SQS Message Level
- **Automatic Retry**: Messages are automatically retried up to 3 times
- **Visibility Timeout**: 15 minutes prevents duplicate processing
- **Dead Letter Queue**: Failed messages moved to DLQ after max retries

#### 3. Lambda Function Level
- **Transient Errors**: Automatic Lambda retry for infrastructure failures
- **Memory Limits**: Garbage collection and memory monitoring
- **Timeout Handling**: Processing stops gracefully before timeout

### Error Categories and Handling

#### Recoverable Errors
- **Network Timeouts**: Retry with exponential backoff
- **Rate Limiting**: Respect rate limits with delays
- **Temporary S3 Errors**: Built-in SDK retries
- **Memory Pressure**: Garbage collection and optimization

#### Non-Recoverable Errors
- **Invalid CSV Format**: Log error and skip processing
- **Missing S3 Objects**: Log error and fail message
- **Invalid URLs**: Skip individual URLs, continue processing
- **Authentication Errors**: Fail immediately with detailed logging

### Dead Letter Queue Processing

**DLQ Message Analysis**:
```python
def analyze_dlq_messages():
    dlq_messages = sqs_processor.get_dlq_messages(max_messages=10)
    
    for message in dlq_messages:
        try:
            body = json.loads(message['Body'])
            logger.info(f"DLQ Message: {body['processing_type']}")
            logger.info(f"Original Timestamp: {body.get('timestamp')}")
            logger.info(f"Failure Reason: Check CloudWatch logs")
            
            # Attempt manual reprocessing if needed
            # reprocess_failed_message(body)
            
        except Exception as e:
            logger.error(f"Failed to analyze DLQ message: {e}")
```

**Manual Reprocessing**:
```python
def reprocess_dlq_message(message_body):
    # Modify message if needed (fix configuration, update URLs, etc.)
    modified_message = {
        **message_body,
        "processing_config": {
            **message_body.get("processing_config", {}),
            "max_retries": 5,  # Increase retries
            "timeout": 60      # Increase timeout
        }
    }
    
    # Send back to main queue
    sqs_processor.send_message(modified_message)
```

## Monitoring and Observability

### CloudWatch Metrics

#### Lambda Metrics
- **Invocations**: Number of Lambda function executions
- **Duration**: Execution time per invocation
- **Errors**: Failed Lambda executions
- **Throttles**: Concurrent execution limit reached
- **Memory Utilization**: Peak memory usage per execution

#### SQS Metrics
- **Messages Sent**: Messages added to queue
- **Messages Received**: Messages consumed from queue
- **Messages Deleted**: Successfully processed messages
- **Messages Visible**: Messages available for processing
- **Messages in Flight**: Messages being processed
- **Dead Letter Queue Size**: Failed messages count

#### Custom Metrics
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

def publish_custom_metrics(creators_processed, images_downloaded, collages_created):
    cloudwatch.put_metric_data(
        Namespace='TikTok/ImageProcessing',
        MetricData=[
            {
                'MetricName': 'CreatorsProcessed',
                'Value': creators_processed,
                'Unit': 'Count'
            },
            {
                'MetricName': 'ImagesDownloaded',
                'Value': images_downloaded,
                'Unit': 'Count'
            },
            {
                'MetricName': 'CollagesCreated',
                'Value': collages_created,
                'Unit': 'Count'
            }
        ]
    )
```

### CloudWatch Alarms

#### Critical Alarms
```yaml
High Error Rate:
  Metric: Lambda Errors
  Threshold: > 5% of invocations
  Period: 5 minutes
  Action: SNS notification

DLQ Messages:
  Metric: SQS Dead Letter Queue Size
  Threshold: > 10 messages
  Period: 5 minutes
  Action: SNS notification + Lambda investigation

Memory Usage:
  Metric: Lambda Memory Utilization
  Threshold: > 80%
  Period: 5 minutes
  Action: Consider memory increase

Function Duration:
  Metric: Lambda Duration
  Threshold: > 10 minutes
  Period: 5 minutes
  Action: Investigate performance issues
```

### Logging Strategy

#### Structured Logging
```python
import logging
import json

logger = logging.getLogger(__name__)

def log_processing_start(message_body):
    logger.info(json.dumps({
        "event": "processing_start",
        "processing_type": message_body.get("processing_type"),
        "s3_key": message_body.get("s3_key"),
        "timestamp": datetime.utcnow().isoformat()
    }))

def log_processing_complete(result):
    logger.info(json.dumps({
        "event": "processing_complete",
        "creators_processed": result.get("total_creators"),
        "collages_created": len(result.get("collages_created", [])),
        "processing_duration": result.get("processing_duration"),
        "timestamp": datetime.utcnow().isoformat()
    }))
```

#### Log Analysis Queries
```sql
-- CloudWatch Insights queries

-- Find processing errors
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 100

-- Calculate average processing time
fields @timestamp, @duration
| filter @type = "REPORT"
| stats avg(@duration) by bin(5m)

-- Monitor memory usage
fields @timestamp, @maxMemoryUsed
| filter @type = "REPORT"
| stats max(@maxMemoryUsed) by bin(5m)
```

## Usage Examples

### Example 1: Processing Large CSV File

**Scenario**: Process 273,455 image URLs from database export

```python
#!/usr/bin/env python3
"""
Process large CSV file using SQS pipeline with parallel batching
"""

from scripts.parallel_processor import ParallelProcessor
import sys

def main():
    csv_file = "/home/geshuhang/aws_image_download/src/cover_urls_20250822_010628.csv"
    
    # Initialize processor
    processor = ParallelProcessor(region='us-east-2')
    
    # Analyze CSV to understand data distribution
    creators, total_images = processor.analyze_csv(csv_file)
    print(f"📊 Found {len(creators)} creators with {total_images} total images")
    
    # Option 1: Parallel S3 upload (fastest, auto-triggers Lambda)
    print("🚀 Using parallel S3 upload method...")
    uploaded_files = processor.process_parallel_s3(csv_file, batch_size=100)
    print(f"✅ Uploaded {len(uploaded_files)} batch files to S3")
    
    # Option 2: Parallel SQS messages (more control)
    # print("🚀 Using parallel SQS message method...")
    # message_ids = processor.process_parallel_sqs(csv_file, batch_size=100)
    # print(f"✅ Sent {len(message_ids)} SQS messages")

if __name__ == "__main__":
    main()
```

### Example 2: Direct SQS Message for Small Dataset

**Scenario**: Process small CSV data directly via SQS message

```python
#!/usr/bin/env python3
"""
Send direct CSV data via SQS message
"""

import boto3
import json
from datetime import datetime

def send_direct_csv_message():
    # Small CSV data
    csv_data = """creator_name,cover_url,created_at
user1,https://example.com/image1.jpg,2025-08-22
user2,https://example.com/image2.jpg,2025-08-22
user3,https://example.com/image3.jpg,2025-08-22"""
    
    # Create SQS message
    message = {
        "processing_type": "csv_data",
        "csv_data": csv_data,
        "processing_config": {
            "rows": 2,
            "cols": 2,
            "quality": 95,
            "max_workers": 4
        },
        "output_prefix": f"collages/{datetime.now().strftime('%Y/%m/%d')}/sqs-trigger/direct-test/",
        "timestamp": datetime.utcnow().isoformat(),
        "source": "manual_test"
    }
    
    # Send to SQS
    sqs = boto3.client('sqs', region_name='us-east-2')
    queue_url = "https://sqs.us-east-2.amazonaws.com/624433616538/tiktok-image-processing-queue"
    
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message)
    )
    
    print(f"✅ Message sent with ID: {response['MessageId']}")

if __name__ == "__main__":
    send_direct_csv_message()
```

### Example 3: Batch Processing with Custom Configuration

**Scenario**: Process CSV with custom grid size and quality settings

```python
#!/usr/bin/env python3
"""
Custom batch processing with specific configuration
"""

from src.sqs_processor import SQSProcessor
from src.config import Config
from datetime import datetime

def custom_batch_processing():
    config = Config()
    sqs_processor = SQSProcessor(config)
    
    # Custom processing configuration
    custom_config = {
        "group_by_creator": True,
        "rows": 6,              # 6x6 grid instead of 5x7
        "cols": 6,
        "max_images_per_creator": 36,
        "quality": 85,          # Lower quality for faster processing
        "max_workers": 12,      # More concurrent downloads
        "timeout": 45,          # Longer timeout for slow networks
        "max_retries": 5        # More retries for reliability
    }
    
    # Generate date-based output prefix
    date_path = datetime.now().strftime('%Y/%m/%d')
    batch_id = datetime.now().strftime('%H%M%S')
    output_prefix = f"collages/{date_path}/sqs-trigger/custom-batch-{batch_id}/"
    
    # Send processing request
    message_id = sqs_processor.send_csv_processing_request(
        csv_s3_bucket="tiktok-image-input",
        csv_s3_key="csv-files/cover_urls_20250822_010628.csv",
        processing_config=custom_config,
        output_prefix=output_prefix
    )
    
    print(f"✅ Custom batch processing started with message ID: {message_id}")
    print(f"📁 Output will be saved to: {output_prefix}")

if __name__ == "__main__":
    custom_batch_processing()
```

### Example 4: Monitoring and DLQ Management

**Scenario**: Monitor processing and handle failed messages

```python
#!/usr/bin/env python3
"""
Monitor SQS pipeline and manage failed messages
"""

import boto3
import json
from src.sqs_processor import SQSProcessor
from src.config import Config

def monitor_pipeline():
    config = Config()
    sqs_processor = SQSProcessor(config)
    
    # Check main queue status
    main_queue_attrs = sqs_processor.get_queue_attributes()
    print("📊 Main Queue Status:")
    print(f"  Messages Available: {main_queue_attrs.get('ApproximateNumberOfMessages', 0)}")
    print(f"  Messages in Flight: {main_queue_attrs.get('ApproximateNumberOfMessagesNotVisible', 0)}")
    
    # Check Dead Letter Queue
    dlq_messages = sqs_processor.get_dlq_messages(max_messages=10)
    if dlq_messages:
        print(f"\n⚠️  Found {len(dlq_messages)} failed messages in DLQ:")
        
        for i, message in enumerate(dlq_messages, 1):
            try:
                body = json.loads(message['Body'])
                print(f"  {i}. Processing Type: {body.get('processing_type')}")
                print(f"     S3 Key: {body.get('s3_key', 'N/A')}")
                print(f"     Timestamp: {body.get('timestamp')}")
                
                # Option to reprocess failed message
                reprocess = input(f"     Reprocess this message? (y/n): ")
                if reprocess.lower() == 'y':
                    reprocess_failed_message(sqs_processor, body, message['ReceiptHandle'])
                    
            except Exception as e:
                print(f"  {i}. Failed to parse message: {e}")
    else:
        print("\n✅ No failed messages in DLQ")

def reprocess_failed_message(sqs_processor, original_body, receipt_handle):
    """Reprocess a failed message with modified configuration"""
    
    # Modify configuration for better success rate
    modified_body = {
        **original_body,
        "processing_config": {
            **original_body.get("processing_config", {}),
            "max_retries": 5,      # More retries
            "timeout": 60,         # Longer timeout
            "max_workers": 4       # Fewer concurrent workers
        },
        "timestamp": datetime.utcnow().isoformat(),
        "source": "dlq_reprocess"
    }
    
    # Send back to main queue
    message_id = sqs_processor.send_message(modified_body)
    if message_id:
        print(f"    ✅ Reprocessed with message ID: {message_id}")
        
        # Delete from DLQ
        sqs_processor.delete_message(receipt_handle, queue_url=sqs_processor.config.SQS_DLQ_URL)
        print(f"    🗑️  Removed from DLQ")
    else:
        print(f"    ❌ Failed to reprocess message")

if __name__ == "__main__":
    monitor_pipeline()
```

## Performance and Optimization

### Throughput Optimization

#### Optimal Batch Sizes
```python
# Recommended batch sizes based on data volume
BATCH_SIZE_RECOMMENDATIONS = {
    "small_dataset": {
        "max_images": 1000,
        "batch_size": 50,
        "description": "Single Lambda execution"
    },
    "medium_dataset": {
        "max_images": 10000,
        "batch_size": 100,
        "description": "Multiple parallel executions"
    },
    "large_dataset": {
        "max_images": 100000,
        "batch_size": 200,
        "description": "Optimized for throughput"
    },
    "very_large_dataset": {
        "max_images": float('inf'),
        "batch_size": 300,
        "description": "Maximum Lambda efficiency"
    }
}

def get_optimal_batch_size(total_images):
    for category, config in BATCH_SIZE_RECOMMENDATIONS.items():
        if total_images <= config["max_images"]:
            return config["batch_size"]
    return BATCH_SIZE_RECOMMENDATIONS["very_large_dataset"]["batch_size"]
```

#### Concurrent Processing Limits
- **Lambda Concurrency**: 50 concurrent executions (configurable)
- **Thread Pool Size**: 8 workers per Lambda (optimal for I/O bound tasks)
- **SQS Batch Size**: 10 messages per Lambda invocation
- **Memory Allocation**: 3008 MB for optimal CPU performance

### Memory Optimization

#### Garbage Collection Strategy
```python
import gc
import psutil

def monitor_memory_usage():
    """Monitor and optimize memory usage during processing"""
    
    # Get current memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    memory_percent = process.memory_percent()
    
    logger.info(f"Memory Usage: {memory_info.rss / 1024 / 1024:.1f} MB ({memory_percent:.1f}%)")
    
    # Trigger garbage collection if memory usage is high
    if memory_percent > 70:
        logger.warning("High memory usage detected, triggering garbage collection")
        gc.collect()
        
        # Check memory after cleanup
        new_memory_info = process.memory_info()
        freed_mb = (memory_info.rss - new_memory_info.rss) / 1024 / 1024
        logger.info(f"Freed {freed_mb:.1f} MB of memory")

def optimize_image_processing():
    """Optimize image processing for memory efficiency"""
    
    # Process images in smaller chunks to reduce memory pressure
    chunk_size = 10  # Process 10 images at a time
    
    for i in range(0, len(urls), chunk_size):
        chunk_urls = urls[i:i + chunk_size]
        
        # Process chunk
        images = download_images_batch(chunk_urls)
        
        # Create partial collage or store temporarily
        process_image_chunk(images)
        
        # Clear references and force garbage collection
        del images
        gc.collect()
        
        # Monitor memory usage
        monitor_memory_usage()
```

### Cost Optimization

#### Lambda Cost Factors
- **Execution Time**: Minimize processing duration
- **Memory Allocation**: Use optimal memory size (3008 MB)
- **Request Count**: Batch processing reduces invocations
- **Data Transfer**: Regional resources minimize transfer costs

#### SQS Cost Factors
- **Message Count**: Batch operations reduce API calls
- **Long Polling**: Reduces empty receive requests
- **Message Size**: Optimize message structure
- **Dead Letter Queue**: Monitor to prevent cost accumulation

#### Cost Calculation Example
```python
def estimate_processing_cost(total_images, creators_count):
    """Estimate AWS costs for processing"""
    
    # Lambda costs (us-east-2 pricing)
    LAMBDA_PRICE_PER_GB_SECOND = 0.0000166667
    LAMBDA_PRICE_PER_REQUEST = 0.0000002
    
    # Estimate processing time and memory
    avg_images_per_creator = total_images / creators_count
    processing_time_per_creator = avg_images_per_creator * 0.5  # 0.5 seconds per image
    memory_gb = 3.008  # 3008 MB
    
    # Calculate Lambda costs
    total_gb_seconds = creators_count * processing_time_per_creator * memory_gb
    lambda_compute_cost = total_gb_seconds * LAMBDA_PRICE_PER_GB_SECOND
    lambda_request_cost = creators_count * LAMBDA_PRICE_PER_REQUEST
    
    # SQS costs (minimal for typical usage)
    sqs_requests = creators_count * 2  # Send + Delete
    sqs_cost = sqs_requests * 0.0000004  # $0.40 per million requests
    
    # S3 costs (storage minimal, requests small)
    s3_put_requests = creators_count  # One collage per creator
    s3_cost = s3_put_requests * 0.0005  # $0.50 per 1000 PUT requests
    
    total_cost = lambda_compute_cost + lambda_request_cost + sqs_cost + s3_cost
    
    return {
        "total_cost": round(total_cost, 4),
        "lambda_compute": round(lambda_compute_cost, 4),
        "lambda_requests": round(lambda_request_cost, 4),
        "sqs_cost": round(sqs_cost, 4),
        "s3_cost": round(s3_cost, 4),
        "cost_per_creator": round(total_cost / creators_count, 6)
    }

# Example for your dataset
cost_estimate = estimate_processing_cost(273455, 7800)  # Estimated creators
print(f"Estimated processing cost: ${cost_estimate['total_cost']}")
print(f"Cost per creator: ${cost_estimate['cost_per_creator']}")
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Messages Stuck in Queue

**Symptoms**:
- Messages remain in queue without processing
- Lambda not being triggered
- High "Messages Visible" count in CloudWatch

**Diagnosis**:
```python
def diagnose_stuck_messages():
    sqs_processor = SQSProcessor(config)
    
    # Check queue attributes
    attrs = sqs_processor.get_queue_attributes()
    print(f"Messages Available: {attrs.get('ApproximateNumberOfMessages')}")
    print(f"Messages in Flight: {attrs.get('ApproximateNumberOfMessagesNotVisible')}")
    print(f"Visibility Timeout: {attrs.get('VisibilityTimeoutSeconds')}")
    
    # Check Lambda event source mapping
    lambda_client = boto3.client('lambda')
    try:
        mappings = lambda_client.list_event_source_mappings(
            FunctionName='image-collage-processor'
        )
        for mapping in mappings['EventSourceMappings']:
            print(f"Event Source: {mapping['EventSourceArn']}")
            print(f"State: {mapping['State']}")
            print(f"Last Processing Result: {mapping.get('LastProcessingResult')}")
    except Exception as e:
        print(f"Error checking event source mappings: {e}")
```

**Solutions**:
- Verify Lambda event source mapping is enabled
- Check Lambda function permissions
- Increase Lambda reserved concurrency
- Verify SQS queue permissions

#### 2. High Memory Usage / Out of Memory

**Symptoms**:
- Lambda functions timing out
- Memory usage > 80%
- Frequent garbage collection logs

**Solutions**:
```python
# Optimize image processing for memory
def memory_optimized_processing(urls, max_memory_mb=2500):
    """Process images with memory constraints"""
    
    # Calculate safe batch size based on available memory
    available_memory = max_memory_mb - get_current_memory_usage()
    estimated_memory_per_image = 5  # MB per image
    safe_batch_size = max(1, available_memory // estimated_memory_per_image)
    
    logger.info(f"Processing in batches of {safe_batch_size} images")
    
    all_images = []
    for i in range(0, len(urls), safe_batch_size):
        batch_urls = urls[i:i + safe_batch_size]
        
        # Process batch
        batch_images = download_images_batch(batch_urls)
        all_images.extend(batch_images)
        
        # Clear batch references
        del batch_images
        gc.collect()
        
        # Check memory usage
        current_memory = get_current_memory_usage()
        if current_memory > max_memory_mb * 0.8:
            logger.warning(f"High memory usage: {current_memory} MB")
            break
    
    return all_images

def get_current_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024
```

#### 3. Image Download Failures

**Symptoms**:
- High number of failed image downloads
- Network timeout errors
- Empty collages or partial collages

**Diagnosis**:
```python
def diagnose_download_failures(urls_sample):
    """Test image URL accessibility"""
    
    failed_urls = []
    success_count = 0
    
    for url in urls_sample[:10]:  # Test first 10 URLs
        try:
            response = requests.head(url, timeout=10)
            if response.status_code == 200:
                success_count += 1
                print(f"✅ {url[:50]}... - {response.status_code}")
            else:
                failed_urls.append((url, response.status_code))
                print(f"❌ {url[:50]}... - {response.status_code}")
        except Exception as e:
            failed_urls.append((url, str(e)))
            print(f"❌ {url[:50]}... - {e}")
    
    print(f"\nSuccess Rate: {success_count}/{len(urls_sample[:10])} ({success_count/10*100:.1f}%)")
    
    if failed_urls:
        print("\nFailed URLs:")
        for url, error in failed_urls:
            print(f"  {url[:60]}... - {error}")
```

**Solutions**:
- Update User-Agent headers for TikTok CDN compatibility
- Increase timeout values
- Implement exponential backoff
- Use different image sources if available

#### 4. DLQ Message Accumulation

**Symptoms**:
- Messages accumulating in Dead Letter Queue
- Repeated processing failures
- High error rate in CloudWatch

**Management Strategy**:
```python
def manage_dlq_messages():
    """Comprehensive DLQ management"""
    
    sqs_processor = SQSProcessor(config)
    dlq_messages = sqs_processor.get_dlq_messages(max_messages=50)
    
    if not dlq_messages:
        print("✅ No messages in DLQ")
        return
    
    print(f"⚠️  Found {len(dlq_messages)} messages in DLQ")
    
    # Analyze failure patterns
    failure_patterns = {}
    for message in dlq_messages:
        try:
            body = json.loads(message['Body'])
            processing_type = body.get('processing_type', 'unknown')
            failure_patterns[processing_type] = failure_patterns.get(processing_type, 0) + 1
        except:
            failure_patterns['parse_error'] = failure_patterns.get('parse_error', 0) + 1
    
    print("\nFailure Patterns:")
    for pattern, count in failure_patterns.items():
        print(f"  {pattern}: {count} messages")
    
    # Offer reprocessing options
    print("\nReprocessing Options:")
    print("1. Reprocess all with increased timeouts")
    print("2. Reprocess only specific type")
    print("3. Archive messages and clear DLQ")
    print("4. Manual inspection")
    
    choice = input("Select option (1-4): ")
    
    if choice == "1":
        reprocess_all_dlq_messages(sqs_processor, dlq_messages)
    elif choice == "2":
        msg_type = input("Enter processing type to reprocess: ")
        reprocess_by_type(sqs_processor, dlq_messages, msg_type)
    elif choice == "3":
        archive_and_clear_dlq(sqs_processor, dlq_messages)
    elif choice == "4":
        manual_dlq_inspection(dlq_messages)

def reprocess_all_dlq_messages(sqs_processor, messages):
    """Reprocess all DLQ messages with modified configuration"""
    
    success_count = 0
    for message in messages:
        try:
            body = json.loads(message['Body'])
            
            # Modify for better success rate
            modified_body = {
                **body,
                "processing_config": {
                    **body.get("processing_config", {}),
                    "max_retries": 5,
                    "timeout": 120,
                    "max_workers": 4
                },
                "source": "dlq_reprocess"
            }
            
            # Send back to main queue
            if sqs_processor.send_message(modified_body):
                sqs_processor.delete_message(
                    message['ReceiptHandle'], 
                    queue_url=sqs_processor.config.SQS_DLQ_URL
                )
                success_count += 1
                
        except Exception as e:
            print(f"Failed to reprocess message: {e}")
    
    print(f"✅ Reprocessed {success_count}/{len(messages)} messages")
```

### Performance Troubleshooting

#### Slow Processing Times

**Diagnostic Queries** (CloudWatch Insights):
```sql
-- Find slowest Lambda executions
fields @timestamp, @duration, @requestId
| filter @type = "REPORT"
| sort @duration desc
| limit 10

-- Analyze memory usage patterns
fields @timestamp, @maxMemoryUsed, @requestId
| filter @type = "REPORT"
| stats avg(@maxMemoryUsed), max(@maxMemoryUsed) by bin(5m)

-- Find error patterns
fields @timestamp, @message, @requestId
| filter @message like /ERROR/
| stats count() by bin(5m)
```

**Optimization Steps**:
1. Increase Lambda memory allocation
2. Optimize image download concurrency
3. Implement caching for repeated URLs
4. Use smaller batch sizes for complex processing

### Network and Connectivity Issues

#### TikTok CDN Access Problems

**Common Issues**:
- Rate limiting from TikTok CDN
- Geographic restrictions
- User-Agent blocking
- SSL/TLS handshake failures

**Solutions**:
```python
# Enhanced headers for TikTok CDN compatibility
ENHANCED_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'image',
    'Sec-Fetch-Mode': 'no-cors',
    'Sec-Fetch-Site': 'cross-site'
}

# Rate limiting implementation
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, max_requests=10, time_window=1):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = defaultdict(list)
    
    def can_make_request(self, domain):
        now = time.time()
        domain_requests = self.requests[domain]
        
        # Remove old requests
        self.requests[domain] = [req_time for req_time in domain_requests 
                                if now - req_time < self.time_window]
        
        # Check if we can make a new request
        if len(self.requests[domain]) < self.max_requests:
            self.requests[domain].append(now)
            return True
        
        return False
    
    def wait_time(self, domain):
        if not self.requests[domain]:
            return 0
        
        oldest_request = min(self.requests[domain])
        return max(0, self.time_window - (time.time() - oldest_request))
```

This comprehensive documentation covers all aspects of the SQS pipeline, from basic concepts to advanced troubleshooting. Use it as a reference for implementing, monitoring, and optimizing your TikTok image processing workflow.
