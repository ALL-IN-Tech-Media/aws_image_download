# S3 Bucket Architecture for TikTok Image Processing

## Required S3 Buckets

You need to create **3 S3 buckets** for the complete image processing pipeline:

### 1. Input Bucket: `tiktok-image-input`
**Purpose**: Store CSV files containing image URLs
**Triggers**: S3 events that automatically invoke Lambda when CSV files are uploaded

### 2. Output Bucket: `tiktok-image-output`  
**Purpose**: Store generated collage images and processing results
**Access**: Where your final collages and results are saved

### 3. Temp Bucket: `tiktok-image-temp` (Optional)
**Purpose**: Temporary storage for intermediate processing files
**Usage**: Can be used for large file processing or debugging

---

## Detailed Bucket Structure

### Input Bucket: `tiktok-image-input`
```
tiktok-image-input/
├── csv-files/
    /version1
│   ├── 2025/
│   │   ├── 01/
│   │   │   ├── 19/
│   │   │   │   ├── cover_urls_20250119_120000.csv
│   │   │   │   ├── cover_urls_20250119_130000.csv
│   │   │   │   └── update_batch_001.csv
│   │   │   └── 20/
│   │   │       └── monthly_batch_20250120.csv
│   │   └── 02/
│   └── manual-uploads/
│       ├── test_batch_001.csv
│       └── emergency_processing.csv
└── archived/
    ├── 2024/
    │   └── processed_files/
    └── failed/
        └── invalid_format_files/
```

**Key Features**:
- **Date-based organization**: `YYYY/MM/DD/` for easy management
- **Manual uploads folder**: For ad-hoc processing
- **Archive system**: Move processed files to avoid reprocessing
- **Failed folder**: Store files that couldn't be processed

### Output Bucket: `tiktok-image-output`
```
tiktok-image-output/
├── collages/
│   ├── 2025/
│   │   ├── 01/
│   │   │   ├── 19/
│   │   │   │   ├── s3-trigger/
│   │   │   │   │   ├── aaliahmaddox_collage_20250119_120530.jpg
│   │   │   │   │   ├── aalijah_collage_20250119_120545.jpg
│   │   │   │   │   └── creator_batch_001/
│   │   │   │   └── sqs-trigger/
│   │   │   │       └── manual_batch_001/
│   │   │   └── 20/
│   │   └── 02/
│   └── by-creator/
│       ├── aaliahmaddox/
│       │   ├── aaliahmaddox_collage_20250119_120530.jpg
│       │   └── aaliahmaddox_collage_20250119_140230.jpg
│       └── aalijah/
│           └── aalijah_collage_20250119_120545.jpg
├── results/
│   ├── processing-summaries/
│   │   ├── 2025/
│   │   │   └── 01/
│   │   │       ├── processing_summary_20250119_120000.json
│   │   │       └── batch_results_20250119.csv
│   └── statistics/
│       ├── daily_stats_20250119.json
│       └── monthly_report_202501.json
├── thumbnails/
│   ├── 2025/
│   │   └── 01/
│   │       └── 19/
│   │           ├── aaliahmaddox_thumb_20250119_120530.jpg
│   │           └── aalijah_thumb_20250119_120545.jpg
└── metadata/
    ├── 2025/
    │   └── 01/
    │       └── 19/
    │           ├── aaliahmaddox_metadata_20250119_120530.json
    │           └── processing_log_20250119.json
```

**Key Features**:
- **Date-based organization**: Same structure as input for easy correlation
- **Trigger-based folders**: Separate S3-triggered vs SQS-triggered results
- **Creator organization**: Alternative view organized by creator name
- **Results tracking**: Processing summaries and statistics
- **Thumbnails**: Smaller versions for quick preview
- **Metadata**: Processing details and logs

### Temp Bucket: `tiktok-image-temp`
```
tiktok-image-temp/
├── processing/
│   ├── lambda-request-123456/
│   │   ├── downloaded_images/
│   │   ├── intermediate_collages/
│   │   └── processing_state.json
│   └── lambda-request-789012/
├── large-files/
│   ├── multipart-uploads/
│   └── chunked-processing/
└── debug/
    ├── failed-downloads/
    ├── error-logs/
    └── memory-dumps/
```

**Key Features**:
- **Request-based isolation**: Each Lambda execution gets its own folder
- **Large file handling**: For files that exceed Lambda memory limits
- **Debug information**: Error logs and diagnostic data
- **Automatic cleanup**: Files older than 7 days are automatically deleted

---

## S3 Bucket Policies and Permissions

### Input Bucket Policy
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowLambdaRead",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::YOUR-ACCOUNT-ID:role/ImageProcessorLambdaRole"
            },
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::tiktok-image-input",
                "arn:aws:s3:::tiktok-image-input/*"
            ]
        },
        {
            "Sid": "AllowS3EventNotification",
            "Effect": "Allow",
            "Principal": {
                "Service": "s3.amazonaws.com"
            },
            "Action": "lambda:InvokeFunction",
            "Resource": "arn:aws:lambda:REGION:YOUR-ACCOUNT-ID:function:image-collage-processor"
        }
    ]
}
```

### Output Bucket Policy
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowLambdaWrite",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::YOUR-ACCOUNT-ID:role/ImageProcessorLambdaRole"
            },
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::tiktok-image-output",
                "arn:aws:s3:::tiktok-image-output/*"
            ]
        }
    ]
}
```

---

## S3 Event Configuration

### Event Notification for Input Bucket
```json
{
    "LambdaConfigurations": [
        {
            "Id": "csv-upload-trigger",
            "LambdaFunctionArn": "arn:aws:lambda:REGION:ACCOUNT-ID:function:image-collage-processor",
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {
                "Key": {
                    "FilterRules": [
                        {
                            "Name": "prefix",
                            "Value": "csv-files/"
                        },
                        {
                            "Name": "suffix",
                            "Value": ".csv"
                        }
                    ]
                }
            }
        }
    ]
}
```

**What this does**:
- Triggers Lambda only for CSV files in the `csv-files/` folder
- Ignores files in `archived/` and `manual-uploads/` unless specifically placed in `csv-files/`
- Processes any CSV file upload automatically

---

## Lifecycle Policies

### Input Bucket Lifecycle
```json
{
    "Rules": [
        {
            "ID": "ArchiveProcessedFiles",
            "Status": "Enabled",
            "Filter": {
                "Prefix": "csv-files/"
            },
            "Transitions": [
                {
                    "Days": 30,
                    "StorageClass": "STANDARD_IA"
                },
                {
                    "Days": 90,
                    "StorageClass": "GLACIER"
                }
            ]
        }
    ]
}
```

### Temp Bucket Lifecycle
```json
{
    "Rules": [
        {
            "ID": "CleanupTempFiles",
            "Status": "Enabled",
            "Filter": {
                "Prefix": "processing/"
            },
            "Expiration": {
                "Days": 7
            }
        }
    ]
}
```

---

## Usage Patterns

### For Small Updates (< 1000 images)
1. Upload CSV to `tiktok-image-input/csv-files/YYYY/MM/DD/`
2. Lambda automatically processes via S3 trigger
3. Results appear in `tiktok-image-output/collages/YYYY/MM/DD/s3-trigger/`

### For Large Monthly Batches (2M+ images)
1. Upload CSV to `tiktok-image-input/csv-files/YYYY/MM/DD/`
2. Send SQS message with batch processing configuration
3. Lambda processes in chunks via SQS trigger
4. Results appear in `tiktok-image-output/collages/YYYY/MM/DD/sqs-trigger/`

### For Manual Processing
1. Upload CSV to `tiktok-image-input/manual-uploads/`
2. Send custom SQS message with specific configuration
3. Results appear in `tiktok-image-output/collages/manual/`

---

## Cost Optimization

### Storage Classes
- **Standard**: Active processing files (first 30 days)
- **Standard-IA**: Archived CSV files (30-90 days)
- **Glacier**: Long-term archive (90+ days)

### Request Optimization
- **Batch operations**: Group small files together
- **Multipart uploads**: For large collage files
- **Transfer acceleration**: For large CSV uploads from your local system

This architecture supports your requirement to process 2M+ images monthly while maintaining organization, cost efficiency, and scalability.
