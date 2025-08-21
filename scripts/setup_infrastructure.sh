#!/bin/bash

# Infrastructure setup script for TikTok Image Processing
# This script creates all required AWS resources using Terraform

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}TikTok Image Processing Infrastructure Setup${NC}"
echo -e "${BLUE}=====================================${NC}"
echo

# Configuration
TERRAFORM_DIR="terraform"
TFVARS_FILE="terraform.tfvars"

# Check prerequisites
echo -e "${GREEN}Checking prerequisites...${NC}"

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}Error: Terraform is not installed.${NC}"
    echo -e "${YELLOW}Please install Terraform from: https://www.terraform.io/downloads.html${NC}"
    exit 1
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed.${NC}"
    echo -e "${YELLOW}Please install AWS CLI from: https://aws.amazon.com/cli/${NC}"
    exit 1
fi

# Check if AWS credentials are configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured.${NC}"
    echo -e "${YELLOW}Please run 'aws configure' to set up your credentials.${NC}"
    exit 1
fi

# Get AWS account info
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)
if [ -z "$AWS_REGION" ]; then
    AWS_REGION="us-east-1"
    echo -e "${YELLOW}Warning: No region configured, using default: $AWS_REGION${NC}"
fi

echo -e "${GREEN}✓ Terraform installed: $(terraform version -json | jq -r '.terraform_version')${NC}"
echo -e "${GREEN}✓ AWS CLI installed: $(aws --version | cut -d' ' -f1)${NC}"
echo -e "${GREEN}✓ AWS Account ID: $AWS_ACCOUNT_ID${NC}"
echo -e "${GREEN}✓ AWS Region: $AWS_REGION${NC}"
echo

# Check if terraform directory exists
if [ ! -d "$TERRAFORM_DIR" ]; then
    echo -e "${RED}Error: Terraform directory not found: $TERRAFORM_DIR${NC}"
    echo -e "${YELLOW}Please ensure you're running this script from the correct directory.${NC}"
    exit 1
fi

# Navigate to terraform directory
cd $TERRAFORM_DIR

# Check if terraform.tfvars exists
if [ ! -f "$TFVARS_FILE" ]; then
    echo -e "${YELLOW}terraform.tfvars not found. Creating from example...${NC}"
    
    if [ -f "terraform.tfvars.example" ]; then
        cp terraform.tfvars.example $TFVARS_FILE
        echo -e "${GREEN}✓ Created terraform.tfvars from example${NC}"
        echo -e "${YELLOW}Please review and customize terraform.tfvars before continuing.${NC}"
        echo -e "${YELLOW}Press Enter to continue or Ctrl+C to exit and edit the file.${NC}"
        read -r
    else
        echo -e "${RED}Error: terraform.tfvars.example not found${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}Terraform configuration files found:${NC}"
ls -la *.tf *.tfvars 2>/dev/null || true
echo

# Initialize Terraform
echo -e "${GREEN}Initializing Terraform...${NC}"
terraform init

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Terraform initialization failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Terraform initialized successfully${NC}"
echo

# Validate Terraform configuration
echo -e "${GREEN}Validating Terraform configuration...${NC}"
terraform validate

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Terraform configuration is invalid${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Terraform configuration is valid${NC}"
echo

# Plan Terraform deployment
echo -e "${GREEN}Creating Terraform plan...${NC}"
terraform plan -var-file="$TFVARS_FILE" -out=tfplan

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Terraform planning failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Terraform plan created successfully${NC}"
echo

# Show what will be created
echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}INFRASTRUCTURE SUMMARY${NC}"
echo -e "${BLUE}=====================================${NC}"
echo

echo -e "${GREEN}The following AWS resources will be created:${NC}"
echo
echo -e "${YELLOW}S3 Buckets:${NC}"
echo "  • tiktok-image-input    (CSV files)"
echo "  • tiktok-image-output   (Generated collages)"
echo "  • tiktok-image-temp     (Temporary processing files)"
echo
echo -e "${YELLOW}SQS Queues:${NC}"
echo "  • tiktok-image-processing-queue  (Main processing queue)"
echo "  • tiktok-image-processing-dlq    (Dead letter queue)"
echo
echo -e "${YELLOW}IAM Resources:${NC}"
echo "  • ImageProcessorLambdaRole       (Lambda execution role)"
echo "  • Custom policies for S3 and SQS access"
echo
echo -e "${YELLOW}CloudWatch:${NC}"
echo "  • Log group for Lambda function"
echo "  • Log retention policies"
echo
echo -e "${YELLOW}S3 Lifecycle Policies:${NC}"
echo "  • Automatic transition to cheaper storage classes"
echo "  • Cleanup of temporary files"
echo

# Confirm deployment
echo -e "${YELLOW}Do you want to proceed with creating these resources? (y/N)${NC}"
read -r CONFIRM

if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Deployment cancelled by user${NC}"
    exit 0
fi

# Apply Terraform configuration
echo -e "${GREEN}Applying Terraform configuration...${NC}"
terraform apply tfplan

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Terraform apply failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Infrastructure deployed successfully!${NC}"
echo

# Get outputs
echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}DEPLOYMENT RESULTS${NC}"
echo -e "${BLUE}=====================================${NC}"
echo

echo -e "${GREEN}Created Resources:${NC}"
echo

# Extract outputs
INPUT_BUCKET=$(terraform output -raw input_bucket_name)
OUTPUT_BUCKET=$(terraform output -raw output_bucket_name)
TEMP_BUCKET=$(terraform output -raw temp_bucket_name)
PROCESSING_QUEUE_URL=$(terraform output -raw processing_queue_url)
DLQ_URL=$(terraform output -raw dead_letter_queue_url)
LAMBDA_ROLE_ARN=$(terraform output -raw lambda_execution_role_arn)

echo -e "${YELLOW}S3 Buckets:${NC}"
echo "  Input:  $INPUT_BUCKET"
echo "  Output: $OUTPUT_BUCKET"
echo "  Temp:   $TEMP_BUCKET"
echo

echo -e "${YELLOW}SQS Queues:${NC}"
echo "  Processing: $PROCESSING_QUEUE_URL"
echo "  Dead Letter: $DLQ_URL"
echo

echo -e "${YELLOW}IAM Role:${NC}"
echo "  Lambda Role: $LAMBDA_ROLE_ARN"
echo

# Create environment file for deployment script
echo -e "${GREEN}Creating environment configuration...${NC}"
cd ..

cat > .env << EOF
# AWS Infrastructure Configuration
# Generated by setup_infrastructure.sh on $(date)

# S3 Buckets
INPUT_BUCKET=$INPUT_BUCKET
OUTPUT_BUCKET=$OUTPUT_BUCKET
TEMP_BUCKET=$TEMP_BUCKET

# SQS Queues
SQS_QUEUE_URL=$PROCESSING_QUEUE_URL
SQS_DLQ_URL=$DLQ_URL

# IAM
LAMBDA_ROLE_ARN=$LAMBDA_ROLE_ARN

# AWS Region
AWS_REGION=$AWS_REGION
AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID
EOF

echo -e "${GREEN}✓ Environment configuration saved to .env${NC}"
echo

# Test S3 bucket access
echo -e "${GREEN}Testing S3 bucket access...${NC}"

# Test input bucket
aws s3 ls s3://$INPUT_BUCKET/ &> /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Input bucket accessible${NC}"
else
    echo -e "${YELLOW}⚠ Input bucket access test failed (this is normal for new buckets)${NC}"
fi

# Test output bucket
aws s3 ls s3://$OUTPUT_BUCKET/ &> /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Output bucket accessible${NC}"
else
    echo -e "${YELLOW}⚠ Output bucket access test failed (this is normal for new buckets)${NC}"
fi

echo

# Create sample folder structure
echo -e "${GREEN}Creating sample folder structure...${NC}"

# Create folders in input bucket
aws s3api put-object --bucket $INPUT_BUCKET --key csv-files/ --content-length 0 &> /dev/null
aws s3api put-object --bucket $INPUT_BUCKET --key manual-uploads/ --content-length 0 &> /dev/null
aws s3api put-object --bucket $INPUT_BUCKET --key archived/ --content-length 0 &> /dev/null

# Create folders in output bucket
aws s3api put-object --bucket $OUTPUT_BUCKET --key collages/ --content-length 0 &> /dev/null
aws s3api put-object --bucket $OUTPUT_BUCKET --key results/ --content-length 0 &> /dev/null
aws s3api put-object --bucket $OUTPUT_BUCKET --key thumbnails/ --content-length 0 &> /dev/null

echo -e "${GREEN}✓ Sample folder structure created${NC}"
echo

# Next steps
echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}NEXT STEPS${NC}"
echo -e "${BLUE}=====================================${NC}"
echo

echo -e "${GREEN}Infrastructure setup complete! Next steps:${NC}"
echo
echo "1. ${YELLOW}Deploy Lambda Function:${NC}"
echo "   ./deploy.sh"
echo
echo "2. ${YELLOW}Test with a sample CSV:${NC}"
echo "   aws s3 cp your_csv_file.csv s3://$INPUT_BUCKET/csv-files/"
echo
echo "3. ${YELLOW}Send SQS message for manual processing:${NC}"
echo "   aws sqs send-message --queue-url $PROCESSING_QUEUE_URL --message-body '{\"processing_type\":\"csv_s3\",\"s3_bucket\":\"$INPUT_BUCKET\",\"s3_key\":\"csv-files/your_file.csv\"}'"
echo
echo "4. ${YELLOW}Monitor processing:${NC}"
echo "   aws logs tail /aws/lambda/image-collage-processor --follow"
echo
echo "5. ${YELLOW}Check results:${NC}"
echo "   aws s3 ls s3://$OUTPUT_BUCKET/collages/ --recursive"
echo

echo -e "${GREEN}Configuration files created:${NC}"
echo "  • .env                    (Environment variables)"
echo "  • terraform/terraform.tfvars (Terraform configuration)"
echo

echo -e "${YELLOW}Important Notes:${NC}"
echo "  • Keep your terraform.tfvars file secure (contains configuration)"
echo "  • The .env file contains your AWS resource names for deployment"
echo "  • S3 bucket names are globally unique and cannot be changed easily"
echo "  • Lifecycle policies will automatically manage storage costs"
echo

echo -e "${GREEN}Infrastructure setup completed successfully!${NC}"
