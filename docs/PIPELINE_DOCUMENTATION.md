# TikTok Image Processing Pipeline - Detailed Documentation

## Overview

This project creates a scalable AWS-based pipeline for processing TikTok image URLs and generating collages. The system is designed to handle both small incremental updates and large monthly batches (2M+ images).

## Pipeline Architecture

### Phase 1: Data Extraction (Local)

**Component**: `get_urls.py`
**Location**: Local system
**Purpose**: Extract image URLs from MySQL database

**Process**:
1. **Database Connection**: Connects to local MySQL database `tiktok_creator.videos_links`
2. **Data Filtering**: Applies date and creator filters to extract relevant records
3. **URL Processing**: Parses JSON-formatted cover URLs from database records
4. **CSV Generation**: Creates structured CSV files with format:
   ```
   creator_name,cover_url,created_at
   aaliahmaddox,https://tiktokcdn-us.com/...,2025-01-19 12:00:00
   ```

**Key Features**:
- Date range filtering (last_X_days, custom ranges)
- Creator-specific filtering
- JSON URL parsing with error handling
- Timestamped output files

### Phase 2: Input Methods (AWS)

The system supports two input methods for different use cases:

#### Method 1: S3 Direct Upload (Automatic Processing)
**Use Case**: Small updates, regular processing
**Process**:
1. Upload CSV file to S3 bucket `tiktok-image-input/csv-files/`
2. S3 Event Notification automatically triggers Lambda
3. Lambda processes immediately

#### Method 2: SQS Message Trigger (Controlled Processing)
**Use Case**: Large batches, scheduled processing, custom configuration
**Process**:
1. Upload CSV to S3 (any location)
2. Send SQS message with processing configuration
3. Lambda polls SQS queue and processes on demand

### Phase 3: AWS Infrastructure Layer

#### S3 Storage Architecture

**Input Bucket** (`tiktok-image-input`):
```
csv-files/                 # Auto-processed files
├── 2025/01/19/
│   ├── cover_urls_20250119_120000.csv
│   └── monthly_batch.csv
manual-uploads/            # Manual processing files
archived/                  # Processed files archive
└── failed/               # Failed processing files
```

**Output Bucket** (`tiktok-image-output`):
```
collages/
├── 2025/01/19/
│   ├── s3-trigger/       # S3 auto-triggered results
│   │   ├── aaliahmaddox_collage_20250119_120530.jpg
│   │   └── aalijah_collage_20250119_120545.jpg
│   └── sqs-trigger/      # SQS-triggered results
│       └── batch_001/
results/
├── processing-summaries/  # Processing statistics
└── statistics/           # Performance metrics
```

**Temp Bucket** (`tiktok-image-temp`):
```
processing/
├── lambda-request-123456/ # Per-execution workspace
│   ├── downloaded_images/
│   └── processing_state.json
debug/                     # Error logs and diagnostics
```

#### Message Queue System

**Main Queue** (`image-processing-queue`):
- Standard SQS queue for processing requests
- 14-day message retention
- 15-minute visibility timeout (matches Lambda timeout)
- Long polling enabled for cost optimization

**Dead Letter Queue** (`image-processing-dlq`):
- Captures failed messages after 3 retry attempts
- Manual inspection and reprocessing capability
- 14-day retention for analysis

### Phase 4: Lambda Processing Engine

**Function**: `image-collage-processor`
**Runtime**: Python 3.11
**Memory**: 3008 MB (maximum for CPU optimization)
**Timeout**: 15 minutes
**Concurrency**: 50 (configurable)

#### Processing Components

**1. Lambda Handler** (`lambda_function.py`):
- Event source detection (S3 vs SQS)
- Message parsing and validation
- Error handling and routing
- Response formatting

**2. Image Processor** (`aws_image_processor.py`):
- Adapted from original `image_concat.py`
- Memory-optimized for Lambda environment
- S3 integration for output storage
- Performance monitoring

**3. S3 Utilities** (`s3_utils.py`):
- CSV download from S3
- Image upload to S3
- Presigned URL generation
- Multipart upload support for large files

**4. SQS Processor** (`sqs_processor.py`):
- Message parsing and validation
- Batch message handling
- Dead letter queue management
- Message acknowledgment

**5. Configuration Manager** (`config.py`):
- Environment variable management
- Processing parameter validation
- AWS service configuration
- Runtime optimization settings

### Phase 5: Image Processing Workflow

#### Step 1: Input Processing
**Process**:
1. **Event Detection**: Lambda determines trigger source (S3 or SQS)
2. **CSV Parsing**: Downloads and parses CSV data
3. **Data Validation**: Validates URLs and creator information
4. **Grouping**: Groups URLs by creator (if configured)

#### Step 2: Image Download
**Process** (`download_images_batch`):
1. **Concurrent Downloads**: Uses ThreadPoolExecutor (8 workers default)
2. **Retry Logic**: 3 retry attempts with exponential backoff
3. **Validation**: Checks content type, image dimensions, format
4. **Memory Management**: Monitors Lambda memory usage

**Features**:
- HTTP headers for TikTok CDN compatibility
- Content-type validation
- Minimum size filtering (50x50 pixels)
- Format conversion (RGBA → RGB)

#### Step 3: Collage Creation
**Process** (`create_image_collage_s3`):
1. **Dimension Calculation**: Determines optimal image sizes
2. **Canvas Creation**: Creates grid canvas (default 5x7)
3. **Image Placement**: Resizes and positions images
4. **Memory Optimization**: Garbage collection between operations
5. **Quality Control**: JPEG compression with configurable quality

**Configuration**:
- Grid size: 5 rows × 7 columns (35 images per collage)
- Image quality: 95% JPEG compression
- Background: White fill for empty cells
- Format: JPEG with optimization

#### Step 4: Output Storage
**Process**:
1. **S3 Upload**: Stores collages in organized folder structure
2. **Metadata Generation**: Creates processing statistics
3. **Presigned URLs**: Generates temporary access URLs
4. **Result Tracking**: Records success/failure statistics

### Phase 6: Monitoring and Observability

#### CloudWatch Integration
**Logs**:
- Function execution logs
- Error tracking and stack traces
- Performance metrics
- Memory usage monitoring

**Metrics**:
- Processing duration per creator
- Success/failure rates
- Memory utilization
- Concurrent execution counts

**Alarms**:
- Error rate > 5%
- Function duration > 10 minutes
- Memory usage > 80%
- Dead letter queue messages > 10

### Phase 7: Cost Optimization

#### S3 Lifecycle Policies
**Input Bucket**:
- 30 days: Move to Standard-IA
- 90 days: Move to Glacier
- 365 days: Move to Deep Archive

**Output Bucket**:
- 90 days: Move to Standard-IA
- 365 days: Move to Glacier

**Temp Bucket**:
- 7 days: Delete processing files
- 30 days: Delete debug files

#### Lambda Optimization
- Memory allocation based on actual usage
- Reserved concurrency to control costs
- Efficient image processing algorithms
- Memory garbage collection

## Data Flow Examples

### Small Update Processing (< 1000 images)
```
1. Local: get_urls.py → CSV (100 URLs)
2. Upload: CSV → s3://tiktok-image-input/csv-files/2025/01/19/
3. Trigger: S3 Event → Lambda (automatic)
4. Process: Lambda downloads images, creates collages
5. Output: Collages → s3://tiktok-image-output/collages/2025/01/19/s3-trigger/
6. Duration: ~5-10 minutes
```

### Large Batch Processing (2M+ images)
```
1. Local: get_urls.py → CSV (2M URLs)
2. Upload: CSV → s3://tiktok-image-input/csv-files/2025/01/19/
3. Trigger: SQS Message with batch configuration
4. Process: Lambda processes in chunks (multiple executions)
5. Output: Collages → s3://tiktok-image-output/collages/2025/01/19/sqs-trigger/
6. Duration: ~2-4 hours (parallel processing)
```

## Performance Characteristics

### Throughput
- **Single Lambda**: ~35 images per execution (one collage)
- **Concurrent Processing**: 50 Lambda executions simultaneously
- **Monthly Capacity**: 2M+ images with optimized batching

### Latency
- **Small batches**: 5-10 minutes end-to-end
- **Large batches**: 2-4 hours with parallel processing
- **Cold start**: ~2-3 seconds for Lambda initialization

### Cost Optimization
- **S3 Storage**: Automatic lifecycle transitions
- **Lambda**: Pay-per-use with memory optimization
- **SQS**: Long polling reduces API calls
- **Data Transfer**: Optimized with regional resources

## Error Handling and Recovery

### Retry Mechanisms
1. **Image Download**: 3 retries with exponential backoff
2. **SQS Messages**: 3 retries before DLQ
3. **S3 Operations**: Built-in AWS SDK retries
4. **Lambda Execution**: Automatic retry for transient failures

### Failure Scenarios
- **Invalid URLs**: Logged and skipped
- **Network Timeouts**: Retried with backoff
- **Memory Limits**: Automatic garbage collection
- **Processing Failures**: Moved to DLQ for analysis

### Recovery Options
- **DLQ Processing**: Manual reprocessing of failed messages
- **Partial Results**: Successful collages saved even if some fail
- **Debug Information**: Detailed logs for troubleshooting
- **Rollback**: Infrastructure versioning with Terraform

## Security Features

### Access Control
- **IAM Roles**: Least privilege access for Lambda
- **S3 Policies**: Bucket-specific permissions
- **SQS Policies**: Queue access restrictions
- **VPC**: Optional network isolation

### Data Protection
- **Encryption**: S3 and SQS encryption at rest
- **TLS**: All data in transit encrypted
- **Access Logs**: CloudTrail integration
- **Key Rotation**: Automatic KMS key rotation

## Deployment and Maintenance

### Infrastructure as Code
- **Terraform**: Complete infrastructure definition
- **Versioning**: Infrastructure change tracking
- **Validation**: Configuration validation before deployment
- **Rollback**: Easy rollback to previous versions

### Deployment Process
1. **Infrastructure**: `./setup_infrastructure.sh`
2. **Lambda Code**: `./deploy.sh`
3. **Testing**: Automated validation
4. **Monitoring**: CloudWatch dashboard setup

### Maintenance Tasks
- **Log Cleanup**: Automatic retention policies
- **Cost Review**: Monthly cost analysis
- **Performance Tuning**: Regular optimization
- **Security Updates**: Dependency updates

This pipeline provides a robust, scalable solution for processing millions of TikTok images monthly while maintaining cost efficiency and operational reliability.
