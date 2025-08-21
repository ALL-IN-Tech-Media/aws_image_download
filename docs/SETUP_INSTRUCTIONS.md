# AWS Setup Instructions

## Current Status
✅ Terraform installed (v1.5.7)
✅ AWS CLI installed (v2.28.12)
❌ AWS credentials not configured

## Next Steps

### 1. Configure AWS Credentials
You need to configure AWS credentials before proceeding. Run:

```bash
aws configure
```

You'll be prompted to enter:
- **AWS Access Key ID**: Your AWS access key
- **AWS Secret Access Key**: Your AWS secret key  
- **Default region name**: Recommended: `us-east-1`
- **Default output format**: Recommended: `json`

### 2. Get AWS Credentials
If you don't have AWS credentials yet:

1. **Sign in to AWS Console**: https://aws.amazon.com/console/
2. **Go to IAM Service**: Search for "IAM" in the AWS console
3. **Create User**: 
   - Click "Users" → "Create user"
   - Username: `tiktok-image-processor`
   - Access type: "Programmatic access"
4. **Attach Policies**:
   - `AmazonS3FullAccess`
   - `AmazonSQSFullAccess`
   - `AWSLambda_FullAccess`
   - `IAMFullAccess` (for creating roles)
   - `CloudWatchLogsFullAccess`
5. **Download Credentials**: Save the Access Key ID and Secret Access Key

### 3. Test AWS Connection
After configuring credentials, test the connection:

```bash
aws sts get-caller-identity
```

You should see your AWS account ID and user ARN.

### 4. Run Infrastructure Setup
Once AWS credentials are configured:

```bash
./setup_infrastructure.sh
```

This will create all required AWS resources:
- S3 buckets (input, output, temp)
- SQS queues (processing + dead letter)
- IAM roles and policies
- CloudWatch log groups

### 5. Deploy Lambda Function
After infrastructure is created:

```bash
./deploy.sh
```

This will package and deploy your image processing code to AWS Lambda.

### 6. Test the System
After deployment:

```bash
./test_local_upload.py
```

This will test both S3 and SQS triggers with your existing CSV data.

## Important Notes

### Security
- Keep your AWS credentials secure
- Don't commit credentials to version control
- Consider using IAM roles for production

### Cost Management
- The infrastructure includes cost optimization features
- Monitor your AWS billing dashboard
- S3 lifecycle policies will automatically optimize storage costs

### Troubleshooting
If you encounter issues:

1. **Check AWS credentials**: `aws sts get-caller-identity`
2. **Verify region**: Make sure you're using a supported region
3. **Check permissions**: Ensure your AWS user has required permissions
4. **View logs**: Check CloudWatch logs for Lambda execution details

## Current Project Structure

```
aws_image_download/
├── Core Lambda Files
│   ├── lambda_function.py          ✅ Main Lambda handler
│   ├── aws_image_processor.py      ✅ AWS-adapted image processing
│   ├── s3_utils.py                 ✅ S3 file operations
│   ├── sqs_processor.py            ✅ SQS message handling
│   └── config.py                   ✅ Configuration management
├── Deployment Scripts
│   ├── setup_infrastructure.sh     ✅ AWS infrastructure setup
│   ├── deploy.sh                   ✅ Lambda deployment
│   └── test_local_upload.py        ✅ Testing script
├── Infrastructure Code
│   └── terraform/
│       ├── main.tf                 ✅ Main Terraform config
│       ├── variables.tf            ✅ Variable definitions
│       └── terraform.tfvars.example ✅ Example configuration
├── Dependencies
│   └── requirements.txt            ✅ Python dependencies
├── Documentation
│   ├── README.md                   ✅ Complete setup guide
│   ├── PIPELINE_DOCUMENTATION.md  ✅ Detailed pipeline explanation
│   └── s3_bucket_architecture.md  ✅ S3 structure guide
└── Your Existing Files
    ├── get_urls.py                 ✅ Database extraction (unchanged)
    ├── image_concat.py             ✅ Original local processing (unchanged)
    └── cover_urls_*.csv            ✅ Sample data for testing
```

All components are ready for deployment once AWS credentials are configured!
