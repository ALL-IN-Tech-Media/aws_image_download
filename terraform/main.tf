# Terraform configuration for TikTok Image Processing Infrastructure
# This creates all required AWS resources: S3 buckets, SQS queues, IAM roles

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Configure AWS Provider
provider "aws" {
  region = var.aws_region
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local values
locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  
  # Common tags
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    CreatedBy   = "Terraform"
    Purpose     = "TikTok Image Processing"
  }
}

#######################
# S3 BUCKETS
#######################

# Input bucket for CSV files
resource "aws_s3_bucket" "input_bucket" {
  bucket = "${var.project_name}-image-input"
  
  tags = merge(local.common_tags, {
    Name = "Input Bucket"
    Type = "CSV Storage"
  })
}

# Output bucket for collages and results
resource "aws_s3_bucket" "output_bucket" {
  bucket = "${var.project_name}-image-output"
  
  tags = merge(local.common_tags, {
    Name = "Output Bucket"
    Type = "Collage Storage"
  })
}

# Temp bucket for intermediate processing
resource "aws_s3_bucket" "temp_bucket" {
  bucket = "${var.project_name}-image-temp"
  
  tags = merge(local.common_tags, {
    Name = "Temp Bucket"
    Type = "Temporary Storage"
  })
}

#######################
# S3 BUCKET CONFIGURATIONS
#######################

# Input bucket versioning
resource "aws_s3_bucket_versioning" "input_bucket_versioning" {
  bucket = aws_s3_bucket.input_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Output bucket versioning
resource "aws_s3_bucket_versioning" "output_bucket_versioning" {
  bucket = aws_s3_bucket.output_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Temp bucket versioning (disabled for temp files)
resource "aws_s3_bucket_versioning" "temp_bucket_versioning" {
  bucket = aws_s3_bucket.temp_bucket.id
  versioning_configuration {
    status = "Disabled"
  }
}

# Input bucket public access block
resource "aws_s3_bucket_public_access_block" "input_bucket_pab" {
  bucket = aws_s3_bucket.input_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Output bucket public access block
resource "aws_s3_bucket_public_access_block" "output_bucket_pab" {
  bucket = aws_s3_bucket.output_bucket.id

  block_public_acls       = var.enable_public_collages ? false : true
  block_public_policy     = var.enable_public_collages ? false : true
  ignore_public_acls      = var.enable_public_collages ? false : true
  restrict_public_buckets = var.enable_public_collages ? false : true
}

# Temp bucket public access block
resource "aws_s3_bucket_public_access_block" "temp_bucket_pab" {
  bucket = aws_s3_bucket.temp_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#######################
# S3 LIFECYCLE POLICIES
#######################

# Input bucket lifecycle policy
resource "aws_s3_bucket_lifecycle_configuration" "input_bucket_lifecycle" {
  bucket = aws_s3_bucket.input_bucket.id

  rule {
    id     = "archive_processed_csvs"
    status = "Enabled"

    filter {
      prefix = "csv-files/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }
  }

  rule {
    id     = "cleanup_failed_files"
    status = "Enabled"

    filter {
      prefix = "archived/failed/"
    }

    expiration {
      days = 90
    }
  }
}

# Output bucket lifecycle policy
resource "aws_s3_bucket_lifecycle_configuration" "output_bucket_lifecycle" {
  bucket = aws_s3_bucket.output_bucket.id

  rule {
    id     = "transition_old_collages"
    status = "Enabled"

    filter {
      prefix = "collages/"
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }

  rule {
    id     = "cleanup_temp_results"
    status = "Enabled"

    filter {
      prefix = "results/processing-summaries/"
    }

    expiration {
      days = 365
    }
  }
}

# Temp bucket lifecycle policy
resource "aws_s3_bucket_lifecycle_configuration" "temp_bucket_lifecycle" {
  bucket = aws_s3_bucket.temp_bucket.id

  rule {
    id     = "cleanup_processing_files"
    status = "Enabled"

    filter {
      prefix = "processing/"
    }

    expiration {
      days = 7
    }
  }

  rule {
    id     = "cleanup_debug_files"
    status = "Enabled"

    filter {
      prefix = "debug/"
    }

    expiration {
      days = 30
    }
  }

  rule {
    id     = "cleanup_large_files"
    status = "Enabled"

    filter {
      prefix = "large-files/"
    }

    expiration {
      days = 3
    }
  }
}

#######################
# SQS QUEUES
#######################

# Main processing queue
resource "aws_sqs_queue" "processing_queue" {
  name                       = "${var.project_name}-image-processing-queue"
  delay_seconds              = 0
  max_message_size           = 262144  # 256 KB
  message_retention_seconds  = 1209600 # 14 days
  receive_wait_time_seconds  = 20      # Long polling
  visibility_timeout_seconds = 900     # 15 minutes (Lambda timeout)

  # Dead letter queue configuration
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter_queue.arn
    maxReceiveCount     = 3
  })

  tags = merge(local.common_tags, {
    Name = "Processing Queue"
    Type = "Main Queue"
  })
}

# Dead letter queue
resource "aws_sqs_queue" "dead_letter_queue" {
  name                      = "${var.project_name}-image-processing-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = merge(local.common_tags, {
    Name = "Dead Letter Queue"
    Type = "Error Queue"
  })
}

#######################
# IAM ROLES AND POLICIES
#######################

# Lambda execution role
resource "aws_iam_role" "lambda_execution_role" {
  name = "ImageProcessorLambdaRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "Lambda Execution Role"
  })
}

# Lambda basic execution policy attachment
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda SQS execution policy attachment
resource "aws_iam_role_policy_attachment" "lambda_sqs_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

# Custom policy for S3 and SQS access
resource "aws_iam_role_policy" "lambda_s3_sqs_policy" {
  name = "ImageProcessorS3SQSPolicy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:HeadObject"
        ]
        Resource = [
          aws_s3_bucket.input_bucket.arn,
          "${aws_s3_bucket.input_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:HeadObject",
          "s3:ListObjectsV2"
        ]
        Resource = [
          aws_s3_bucket.output_bucket.arn,
          "${aws_s3_bucket.output_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:HeadObject"
        ]
        Resource = [
          aws_s3_bucket.temp_bucket.arn,
          "${aws_s3_bucket.temp_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.creator_processing_state.arn,
          "${aws_dynamodb_table.creator_processing_state.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage"
        ]
        Resource = [
          aws_sqs_queue.processing_queue.arn,
          aws_sqs_queue.dead_letter_queue.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:*"
      }
    ]
  })
}

#######################
# DYNAMODB TABLE
#######################

# Creator processing state table
resource "aws_dynamodb_table" "creator_processing_state" {
  name           = "${var.project_name}-creator-processing-state"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "creator_name"
  range_key      = "processing_date"

  attribute {
    name = "creator_name"
    type = "S"
  }

  attribute {
    name = "processing_date"
    type = "S"
  }

  attribute {
    name = "batch_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  global_secondary_index {
    name            = "batch-id-index"
    hash_key        = "batch_id"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "status-date-index"
    hash_key        = "status"
    range_key       = "processing_date"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Name = "Creator Processing State"
    Type = "State Management"
  })
}

#######################
# CLOUDWATCH LOG GROUP
#######################

resource "aws_cloudwatch_log_group" "lambda_log_group" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "Lambda Log Group"
  })
}

#######################
# OUTPUTS
#######################

output "input_bucket_name" {
  description = "Name of the input S3 bucket"
  value       = aws_s3_bucket.input_bucket.bucket
}

output "output_bucket_name" {
  description = "Name of the output S3 bucket"
  value       = aws_s3_bucket.output_bucket.bucket
}

output "temp_bucket_name" {
  description = "Name of the temp S3 bucket"
  value       = aws_s3_bucket.temp_bucket.bucket
}

output "processing_queue_url" {
  description = "URL of the SQS processing queue"
  value       = aws_sqs_queue.processing_queue.url
}

output "dead_letter_queue_url" {
  description = "URL of the SQS dead letter queue"
  value       = aws_sqs_queue.dead_letter_queue.url
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_execution_role.arn
}

output "lambda_log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.lambda_log_group.name
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB creator processing state table"
  value       = aws_dynamodb_table.creator_processing_state.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB creator processing state table"
  value       = aws_dynamodb_table.creator_processing_state.arn
}
