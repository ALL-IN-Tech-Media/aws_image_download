# TikTok Image Collage Processor

A serverless AWS Lambda-based system for automatically processing TikTok cover images into collages. This system can handle large-scale image processing (2M+ images monthly) with automatic triggers via S3 uploads or SQS messages.

## 🚀 Features

- **Serverless Architecture**: Built on AWS Lambda for automatic scaling
- **Dual Trigger System**: S3 file uploads or SQS message processing
- **High Performance**: Concurrent image downloading and processing
- **Cost Optimized**: S3 lifecycle policies and efficient memory usage
- **Production Ready**: Error handling, retries, and comprehensive logging
- **Flexible Configuration**: Customizable grid sizes, quality, and processing parameters

## 📋 Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Setup](#detailed-setup)
- [Usage](#usage)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Cost Optimization](#cost-optimization)
- [Contributing](#contributing)

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CSV Upload    │    │   SQS Message   │    │  Local Script   │
│   (S3 Trigger)  │    │   (Manual)      │    │  (get_urls.py)  │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS Lambda Function                         │
│                 (image-collage-processor)                      │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Image Processing                           │
│  • Download TikTok images concurrently                        │
│  • Create 5x7 collages (customizable)                         │
│  • Optimize memory usage                                       │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    S3 Output Storage                           │
│  • Organized by creator and timestamp                          │
│  • Lifecycle policies for cost optimization                    │
│  • High-quality JPEG output                                    │
└─────────────────────────────────────────────────────────────────┘
```

## 📦 Prerequisites

### AWS Requirements
- AWS CLI installed and configured
- AWS account with appropriate permissions
- Terraform installed (for infrastructure setup)

### Local Requirements
- Python 3.11+
- MySQL database (for get_urls.py script)
- Bash shell (for deployment scripts)

### Required AWS Permissions
Your AWS user/role needs permissions for:
- Lambda (create, update, invoke)
- S3 (create buckets, read/write objects)
- SQS (create queues, send/receive messages)
- IAM (create roles and policies)
- CloudWatch (create log groups, write logs)

## ⚡ Quick Start

### 1. Clone and Setup
```bash
git clone <your-repo>
cd aws_image_download

# Make scripts executable
chmod +x scripts/*.sh
```

### 2. Configure AWS
```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, and region (recommend us-east-2)
```

### 3. Deploy Infrastructure
```bash
# Setup AWS infrastructure (S3, SQS, IAM)
./scripts/setup_infrastructure.sh

# Deploy Lambda function
./scripts/deploy.sh
```

### 4. Test the System
```bash
# Upload a test CSV file
aws s3 cp examples/sample_csv.csv s3://tiktok-image-input/csv-files/test.csv --region us-east-2

# Check results
aws s3 ls s3://tiktok-image-output/ --recursive --region us-east-2
```

## 🔧 Detailed Setup

### Infrastructure Components

The system creates the following AWS resources:

#### S3 Buckets
- **tiktok-image-input**: CSV file uploads (triggers Lambda)
- **tiktok-image-output**: Generated collages
- **tiktok-image-temp**: Temporary processing files

#### SQS Queues
- **tiktok-image-processing-queue**: Main processing queue
- **tiktok-image-processing-dlq**: Dead letter queue for failed messages

#### Lambda Function
- **image-collage-processor**: Main processing function
- Memory: 3008 MB (maximum for CPU optimization)
- Timeout: 15 minutes
- Runtime: Python 3.11

### Step-by-Step Deployment

#### 1. Infrastructure Setup
```bash
cd terraform/

# Copy and edit configuration
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars  # Edit with your preferences

# Initialize and apply Terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

#### 2. Lambda Deployment
```bash
# Deploy Lambda function with all dependencies
./scripts/deploy.sh
```

The deployment script will:
- Package Python dependencies
- Create deployment package
- Upload to Lambda
- Configure environment variables
- Set up S3 and SQS triggers

#### 3. Verification
```bash
# Test Lambda function
aws lambda invoke \
  --function-name image-collage-processor \
  --payload '{}' \
  response.json \
  --region us-east-2

# Check function status
aws lambda get-function \
  --function-name image-collage-processor \
  --region us-east-2
```

## 📖 Usage

### Method 1: S3 Upload (Automatic Processing)

Upload CSV files to S3 for automatic processing:

```bash
# Upload CSV file
aws s3 cp your_data.csv s3://tiktok-image-input/csv-files/batch-001.csv --region us-east-2

# Processing starts automatically
# Check CloudWatch logs for progress
aws logs tail /aws/lambda/image-collage-processor --since 5m --region us-east-2
```

### Method 2: SQS Message (Manual Processing)

Send processing requests via SQS:

```bash
# Send SQS message
aws sqs send-message \
  --queue-url "https://sqs.us-east-2.amazonaws.com/YOUR-ACCOUNT-ID/tiktok-image-processing-queue" \
  --message-body '{
    "processing_type": "csv_data",
    "csv_data": "creator_name,cover_url,updated_at\ntest_creator,https://picsum.photos/300/300,2025-01-19",
    "processing_config": {
      "rows": 5,
      "cols": 7,
      "quality": 95
    },
    "output_prefix": "manual-batch/"
  }' \
  --region us-east-2
```

### Method 3: Local Script Integration

Use the local `get_urls.py` script to extract data from MySQL:

```bash
# Configure database connection in get_urls.py
python get_urls.py

# Upload generated CSV
aws s3 cp cover_urls_$(date +%Y%m%d_%H%M%S).csv s3://tiktok-image-input/csv-files/ --region us-east-2
```

### CSV Format

Your CSV files must follow this format:

```csv
creator_name,cover_url,updated_at
alice_creator,https://example.com/image1.jpg,2025-01-19
alice_creator,https://example.com/image2.jpg,2025-01-19
bob_creator,https://example.com/image3.jpg,2025-01-19
```

**Requirements:**
- Header row: `creator_name,cover_url,updated_at`
- Valid image URLs (JPEG, PNG, WebP supported)
- Creator names will be used for output file naming

## ⚙️ Configuration

### Environment Variables

The Lambda function uses these environment variables (set automatically by deploy script):

| Variable | Default | Description |
|----------|---------|-------------|
| `INPUT_BUCKET` | tiktok-image-input | S3 bucket for CSV uploads |
| `OUTPUT_BUCKET` | tiktok-image-output | S3 bucket for collages |
| `TEMP_BUCKET` | tiktok-image-temp | S3 bucket for temporary files |
| `DEFAULT_ROWS` | 5 | Default collage rows |
| `DEFAULT_COLS` | 7 | Default collage columns |
| `DEFAULT_QUALITY` | 95 | JPEG quality (1-100) |
| `DEFAULT_MAX_WORKERS` | 8 | Concurrent download workers |
| `DEFAULT_TIMEOUT` | 30 | Download timeout (seconds) |
| `DEFAULT_MAX_RETRIES` | 3 | Download retry attempts |
| `DEFAULT_MAX_IMAGES_PER_CREATOR` | 35 | Max images per collage |

### Processing Configuration

You can customize processing via SQS messages:

```json
{
  "processing_type": "csv_data",
  "csv_data": "...",
  "processing_config": {
    "rows": 6,              // Grid rows
    "cols": 6,              // Grid columns  
    "quality": 90,          // JPEG quality
    "max_workers": 4,       // Concurrent downloads
    "timeout": 45,          // Download timeout
    "max_retries": 2        // Retry attempts
  },
  "output_prefix": "custom-batch/"
}
```

### S3 Bucket Structure

```
tiktok-image-input/
├── csv-files/           # CSV uploads (triggers processing)
└── archive/            # Processed CSV files (lifecycle policy)

tiktok-image-output/
├── s3-trigger/         # S3-triggered processing results
│   └── csv-files/
│       └── {filename}/
│           └── collages/
└── sqs-trigger/        # SQS-triggered processing results
    └── {output_prefix}/
        └── collages/

tiktok-image-temp/
└── downloads/          # Temporary image downloads (auto-cleanup)
```

## 📊 Monitoring

### CloudWatch Logs

Monitor processing in real-time:

```bash
# Tail logs
aws logs tail /aws/lambda/image-collage-processor --follow --region us-east-2

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/image-collage-processor \
  --filter-pattern "ERROR" \
  --region us-east-2
```

### Key Metrics to Monitor

- **Lambda Duration**: Should be under 15 minutes
- **Memory Usage**: Typically 100-400MB for normal batches
- **Error Rate**: Should be near 0%
- **SQS Queue Depth**: Monitor for backlogs

### CloudWatch Dashboards

Create custom dashboards to monitor:
- Lambda invocations and errors
- S3 object counts and sizes
- SQS message metrics
- Processing duration trends

## 🐛 Troubleshooting

### Common Issues

#### 1. Lambda Timeout
**Symptoms**: Function times out after 15 minutes
**Solutions**:
- Reduce batch size
- Increase memory allocation
- Check for slow image downloads

#### 2. Memory Limit Exceeded
**Symptoms**: Lambda runs out of memory
**Solutions**:
- Reduce `max_workers` in processing config
- Limit images per creator
- Optimize image processing

#### 3. Image Download Failures
**Symptoms**: High retry rates, missing images in collages
**Solutions**:
- Check image URL validity
- Increase timeout values
- Verify network connectivity

#### 4. Permission Errors
**Symptoms**: Access denied errors in logs
**Solutions**:
- Verify IAM role permissions
- Check S3 bucket policies
- Ensure Lambda execution role is correct

### Debug Mode

Enable debug logging by setting environment variable:
```bash
aws lambda update-function-configuration \
  --function-name image-collage-processor \
  --environment Variables="{...,ENABLE_DEBUG_LOGGING=true}" \
  --region us-east-2
```

### Log Analysis

Common log patterns to search for:

```bash
# Successful processing
aws logs filter-log-events --log-group-name /aws/lambda/image-collage-processor --filter-pattern "✓ Created collage"

# Download failures  
aws logs filter-log-events --log-group-name /aws/lambda/image-collage-processor --filter-pattern "Failed to download"

# Memory usage
aws logs filter-log-events --log-group-name /aws/lambda/image-collage-processor --filter-pattern "Memory after"
```

## 💰 Cost Optimization

### S3 Lifecycle Policies

The system includes automatic cost optimization:

```json
{
  "Rules": [
    {
      "Id": "TempCleanup",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 1,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 30,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 90
      }
    }
  ]
}
```

### Cost Estimates

**Monthly costs for 2M images:**
- Lambda: ~$50-100 (depends on processing time)
- S3 Storage: ~$20-40 (depends on retention)
- Data Transfer: ~$10-20
- **Total: ~$80-160/month**

### Optimization Tips

1. **Batch Processing**: Process larger batches to reduce Lambda cold starts
2. **Image Optimization**: Use appropriate JPEG quality settings
3. **Lifecycle Policies**: Automatically archive old files
4. **Regional Deployment**: Deploy in the same region as your users
5. **Reserved Capacity**: Consider reserved instances for predictable workloads

## 📁 Project Structure

```
aws_image_download/
├── src/                          # Lambda function source code
│   ├── lambda_function.py        # Main Lambda handler
│   ├── aws_image_processor.py    # Core image processing logic
│   ├── s3_utils.py              # S3 operations
│   ├── sqs_processor.py         # SQS message handling
│   ├── config.py                # Configuration management
│   └── requirements.txt         # Python dependencies
├── scripts/                     # Deployment and setup scripts
│   ├── deploy.sh               # Lambda deployment script
│   └── setup_infrastructure.sh # Infrastructure setup script
├── terraform/                  # Infrastructure as Code
│   ├── main.tf                # Main Terraform configuration
│   ├── variables.tf           # Variable definitions
│   ├── terraform.tfvars.example # Example configuration
│   └── terraform.tfvars       # Your configuration (gitignored)
├── docs/                       # Documentation
│   ├── PIPELINE_DOCUMENTATION.md
│   ├── s3_bucket_architecture.md
│   └── SETUP_INSTRUCTIONS.md
├── examples/                   # Example files and configurations
│   ├── sample_csv.csv         # Sample input CSV
│   ├── sqs_message_example.json # Example SQS message
│   ├── test_local_upload.py   # Local testing script
│   └── s3-notification.json   # S3 notification configuration
├── image_concat.py            # Original local processing script
├── get_urls.py               # Local MySQL data extraction script
└── README.md                 # This file
```

## 🤝 Contributing

### Development Setup

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**
4. **Test thoroughly**
   ```bash
   # Test locally
   python -m pytest tests/
   
   # Test Lambda deployment
   ./scripts/deploy.sh
   ```
5. **Submit a pull request**

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings for all functions
- Include error handling and logging

### Testing

Before submitting changes:

1. **Test with sample data**
2. **Verify all triggers work**
3. **Check CloudWatch logs**
4. **Monitor memory and performance**

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

### Getting Help

1. **Check the logs**: Most issues can be diagnosed from CloudWatch logs
2. **Review this README**: Comprehensive troubleshooting section
3. **Check AWS documentation**: For service-specific issues
4. **Create an issue**: For bugs or feature requests

### Useful AWS Documentation

- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/)
- [Amazon S3 User Guide](https://docs.aws.amazon.com/s3/latest/userguide/)
- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/sqs/latest/dg/)
- [AWS CLI Command Reference](https://docs.aws.amazon.com/cli/latest/reference/)

---

**Built with ❤️ for scalable TikTok image processing**