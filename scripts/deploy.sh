#!/bin/bash

# AWS Lambda deployment script for TikTok image collage processor
# This script packages and deploys the Lambda function

set -e  # Exit on any error

# Configuration
FUNCTION_NAME="image-collage-processor"
RUNTIME="python3.11"
HANDLER="lambda_function.lambda_handler"
TIMEOUT=900  # 15 minutes
MEMORY_SIZE=3008  # Maximum memory for CPU optimization
ROLE_NAME="ImageProcessorLambdaRole"
DEPLOYMENT_PACKAGE="lambda-deployment-package.zip"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Lambda deployment process...${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Check if AWS credentials are configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured. Please run 'aws configure' first.${NC}"
    exit 1
fi

# Get AWS account ID and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)
if [ -z "$AWS_REGION" ]; then
    AWS_REGION="us-east-1"
    echo -e "${YELLOW}Warning: No region configured, using default: $AWS_REGION${NC}"
fi

echo -e "${GREEN}AWS Account ID: $AWS_ACCOUNT_ID${NC}"
echo -e "${GREEN}AWS Region: $AWS_REGION${NC}"

# Create deployment directory
DEPLOY_DIR="lambda_deployment"
echo -e "${GREEN}Creating deployment directory: $DEPLOY_DIR${NC}"
rm -rf $DEPLOY_DIR
mkdir -p $DEPLOY_DIR

# Copy Lambda function files
echo -e "${GREEN}Copying Lambda function files...${NC}"
cp src/lambda_function.py $DEPLOY_DIR/
cp src/aws_image_processor.py $DEPLOY_DIR/
cp src/s3_utils.py $DEPLOY_DIR/
cp src/sqs_processor.py $DEPLOY_DIR/
cp src/config.py $DEPLOY_DIR/
cp src/requirements.txt $DEPLOY_DIR/

# Install dependencies
echo -e "${GREEN}Installing Python dependencies...${NC}"
cd $DEPLOY_DIR
pip install -r requirements.txt -t .

# Remove unnecessary files to reduce package size
echo -e "${GREEN}Cleaning up unnecessary files...${NC}"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Create deployment package
echo -e "${GREEN}Creating deployment package: $DEPLOYMENT_PACKAGE${NC}"
zip -r ../$DEPLOYMENT_PACKAGE . -q
cd ..

# Get package size
PACKAGE_SIZE=$(stat -f%z "$DEPLOYMENT_PACKAGE" 2>/dev/null || stat -c%s "$DEPLOYMENT_PACKAGE")
PACKAGE_SIZE_MB=$((PACKAGE_SIZE / 1024 / 1024))
echo -e "${GREEN}Deployment package size: ${PACKAGE_SIZE_MB}MB${NC}"

if [ $PACKAGE_SIZE_MB -gt 50 ]; then
    echo -e "${YELLOW}Warning: Package size is ${PACKAGE_SIZE_MB}MB. Consider optimizing if deployment fails.${NC}"
fi

# Check if IAM role exists
echo -e "${GREEN}Checking IAM role: $ROLE_NAME${NC}"
ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$ROLE_NAME"

if ! aws iam get-role --role-name $ROLE_NAME &> /dev/null; then
    echo -e "${YELLOW}IAM role $ROLE_NAME does not exist. Please create it first or run the infrastructure setup.${NC}"
    echo -e "${YELLOW}Required role ARN: $ROLE_ARN${NC}"
    exit 1
else
    echo -e "${GREEN}IAM role found: $ROLE_ARN${NC}"
fi

# Check if Lambda function exists
echo -e "${GREEN}Checking if Lambda function exists: $FUNCTION_NAME${NC}"

if aws lambda get-function --function-name $FUNCTION_NAME &> /dev/null; then
    echo -e "${GREEN}Function exists. Updating function code...${NC}"
    
    # Update function code
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$DEPLOYMENT_PACKAGE
    
    # Update function configuration
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --handler $HANDLER \
        --timeout $TIMEOUT \
        --memory-size $MEMORY_SIZE \
        --environment Variables="{
            INPUT_BUCKET=tiktok-image-input,
            OUTPUT_BUCKET=tiktok-image-output,
            TEMP_BUCKET=tiktok-image-temp,
            LOG_LEVEL=INFO,
            ENABLE_DEBUG_LOGGING=false,
            DEFAULT_ROWS=5,
            DEFAULT_COLS=7,
            DEFAULT_QUALITY=95,
            DEFAULT_MAX_WORKERS=8,
            DEFAULT_TIMEOUT=30,
            DEFAULT_MAX_RETRIES=3,
            DEFAULT_MAX_IMAGES_PER_CREATOR=35
        }"
    
    echo -e "${GREEN}Function updated successfully!${NC}"
    
else
    echo -e "${GREEN}Function does not exist. Creating new function...${NC}"
    
    # Create new function
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler $HANDLER \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --timeout $TIMEOUT \
        --memory-size $MEMORY_SIZE \
        --environment Variables="{
            INPUT_BUCKET=tiktok-image-input,
            OUTPUT_BUCKET=tiktok-image-output,
            TEMP_BUCKET=tiktok-image-temp,
            LOG_LEVEL=INFO,
            ENABLE_DEBUG_LOGGING=false,
            DEFAULT_ROWS=5,
            DEFAULT_COLS=7,
            DEFAULT_QUALITY=95,
            DEFAULT_MAX_WORKERS=8,
            DEFAULT_TIMEOUT=30,
            DEFAULT_MAX_RETRIES=3,
            DEFAULT_MAX_IMAGES_PER_CREATOR=35
        }" \
        --description "TikTok image collage processor for AWS Lambda"
    
    echo -e "${GREEN}Function created successfully!${NC}"
fi

# Set up S3 trigger (if buckets exist)
echo -e "${GREEN}Checking S3 buckets and setting up triggers...${NC}"

INPUT_BUCKET="tiktok-image-input"
if aws s3api head-bucket --bucket $INPUT_BUCKET 2>/dev/null; then
    echo -e "${GREEN}Setting up S3 trigger for bucket: $INPUT_BUCKET${NC}"
    
    # Add permission for S3 to invoke Lambda
    aws lambda add-permission \
        --function-name $FUNCTION_NAME \
        --principal s3.amazonaws.com \
        --action lambda:InvokeFunction \
        --source-arn arn:aws:s3:::$INPUT_BUCKET \
        --statement-id s3-trigger-permission 2>/dev/null || echo -e "${YELLOW}Permission already exists${NC}"
    
    # Create notification configuration
    cat > s3-notification.json << EOF
{
    "LambdaConfigurations": [
        {
            "Id": "csv-upload-trigger",
            "LambdaFunctionArn": "arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT_ID:function:$FUNCTION_NAME",
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {
                "Key": {
                    "FilterRules": [
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
EOF
    
    # Apply notification configuration
    aws s3api put-bucket-notification-configuration \
        --bucket $INPUT_BUCKET \
        --notification-configuration file://s3-notification.json
    
    rm s3-notification.json
    echo -e "${GREEN}S3 trigger configured successfully!${NC}"
else
    echo -e "${YELLOW}Input bucket $INPUT_BUCKET does not exist. S3 trigger not configured.${NC}"
fi

# Set up SQS trigger (if queue exists)
echo -e "${GREEN}Checking SQS queue and setting up triggers...${NC}"

SQS_QUEUE_NAME="image-processing-queue"
SQS_QUEUE_URL=$(aws sqs get-queue-url --queue-name $SQS_QUEUE_NAME --output text --query QueueUrl 2>/dev/null || echo "")

if [ ! -z "$SQS_QUEUE_URL" ]; then
    echo -e "${GREEN}Setting up SQS trigger for queue: $SQS_QUEUE_NAME${NC}"
    
    # Get queue ARN
    SQS_QUEUE_ARN=$(aws sqs get-queue-attributes --queue-url $SQS_QUEUE_URL --attribute-names QueueArn --output text --query Attributes.QueueArn)
    
    # Create event source mapping
    aws lambda create-event-source-mapping \
        --function-name $FUNCTION_NAME \
        --event-source-arn $SQS_QUEUE_ARN \
        --batch-size 10 \
        --maximum-batching-window-in-seconds 5 2>/dev/null || echo -e "${YELLOW}Event source mapping already exists${NC}"
    
    echo -e "${GREEN}SQS trigger configured successfully!${NC}"
else
    echo -e "${YELLOW}SQS queue $SQS_QUEUE_NAME does not exist. SQS trigger not configured.${NC}"
fi

# Clean up
echo -e "${GREEN}Cleaning up deployment files...${NC}"
rm -rf $DEPLOY_DIR
rm -f $DEPLOYMENT_PACKAGE

# Display function information
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}Function details:${NC}"
aws lambda get-function --function-name $FUNCTION_NAME --query 'Configuration.[FunctionName,Runtime,Handler,Timeout,MemorySize,LastModified]' --output table

echo -e "${GREEN}To test the function, you can use:${NC}"
echo -e "${YELLOW}aws lambda invoke --function-name $FUNCTION_NAME --payload '{}' response.json${NC}"

echo -e "${GREEN}To view logs:${NC}"
echo -e "${YELLOW}aws logs describe-log-groups --log-group-name-prefix /aws/lambda/$FUNCTION_NAME${NC}"

echo -e "${GREEN}Deployment script completed!${NC}"
