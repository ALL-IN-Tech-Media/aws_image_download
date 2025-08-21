"""
S3 utilities for AWS Lambda image processing
Handles S3 file operations including CSV downloads and image uploads
"""

import boto3
import csv
import io
import logging
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError, NoCredentialsError
import mimetypes

from config import Config

logger = logging.getLogger(__name__)

class S3Utils:
    """S3 utility class for file operations"""
    
    def __init__(self, config: 'Config'):
        """
        Initialize S3 utilities
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.s3_client = boto3.client('s3')
        
    def download_csv_from_s3(self, bucket_name: str, object_key: str) -> Optional[str]:
        """
        Download CSV file from S3 and return as string
        
        Args:
            bucket_name: S3 bucket name
            object_key: S3 object key
            
        Returns:
            CSV content as string or None if failed
        """
        try:
            logger.info(f"Downloading CSV from s3://{bucket_name}/{object_key}")
            
            response = self.s3_client.get_object(Bucket=bucket_name, Key=object_key)
            csv_content = response['Body'].read().decode('utf-8')
            
            logger.info(f"Successfully downloaded CSV: {len(csv_content)} characters")
            return csv_content
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"CSV file not found: s3://{bucket_name}/{object_key}")
            elif error_code == 'NoSuchBucket':
                logger.error(f"S3 bucket not found: {bucket_name}")
            else:
                logger.error(f"S3 error downloading CSV: {e}")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error downloading CSV: {e}")
            return None
    
    def upload_file_to_s3(self, file_buffer: io.BytesIO, s3_key: str, 
                         content_type: str = 'application/octet-stream',
                         metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Upload file buffer to S3
        
        Args:
            file_buffer: File buffer to upload
            s3_key: S3 key for the file
            content_type: MIME content type
            metadata: Optional metadata dictionary
            
        Returns:
            True if upload successful, False otherwise
        """
        try:
            bucket_name = self.config.OUTPUT_BUCKET
            
            # Prepare upload arguments
            upload_args = {
                'Bucket': bucket_name,
                'Key': s3_key,
                'Body': file_buffer,
                'ContentType': content_type
            }
            
            # Add metadata if provided
            if metadata:
                upload_args['Metadata'] = metadata
            
            # Add ACL for public read if configured
            if self.config.S3_PUBLIC_READ:
                upload_args['ACL'] = 'public-read'
            
            logger.info(f"Uploading file to s3://{bucket_name}/{s3_key}")
            
            self.s3_client.put_object(**upload_args)
            
            logger.info(f"Successfully uploaded file: s3://{bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 error uploading file: {e}")
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error uploading file: {e}")
            return False
    
    def upload_csv_to_s3(self, csv_data: List[Dict[str, Any]], s3_key: str) -> bool:
        """
        Upload CSV data to S3
        
        Args:
            csv_data: List of dictionaries to write as CSV
            s3_key: S3 key for the CSV file
            
        Returns:
            True if upload successful, False otherwise
        """
        try:
            if not csv_data:
                logger.warning("No CSV data to upload")
                return False
            
            # Create CSV in memory
            csv_buffer = io.StringIO()
            fieldnames = csv_data[0].keys()
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(csv_data)
            
            # Convert to bytes
            csv_bytes = io.BytesIO(csv_buffer.getvalue().encode('utf-8'))
            
            # Upload to S3
            return self.upload_file_to_s3(
                file_buffer=csv_bytes,
                s3_key=s3_key,
                content_type='text/csv'
            )
            
        except Exception as e:
            logger.error(f"Error uploading CSV to S3: {e}")
            return False
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate presigned URL for S3 object
        
        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default 1 hour)
            
        Returns:
            Presigned URL or None if failed
        """
        try:
            bucket_name = self.config.OUTPUT_BUCKET
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            logger.debug(f"Generated presigned URL for s3://{bucket_name}/{s3_key}")
            return url
            
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None
    
    def list_objects_with_prefix(self, prefix: str, max_keys: int = 1000) -> List[Dict[str, Any]]:
        """
        List S3 objects with given prefix
        
        Args:
            prefix: S3 key prefix to filter objects
            max_keys: Maximum number of objects to return
            
        Returns:
            List of object metadata dictionaries
        """
        try:
            bucket_name = self.config.INPUT_BUCKET
            
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            objects = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    objects.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                        'etag': obj['ETag']
                    })
            
            logger.info(f"Found {len(objects)} objects with prefix: {prefix}")
            return objects
            
        except ClientError as e:
            logger.error(f"Error listing S3 objects: {e}")
            return []
    
    def delete_object(self, s3_key: str, bucket_name: Optional[str] = None) -> bool:
        """
        Delete S3 object
        
        Args:
            s3_key: S3 object key to delete
            bucket_name: S3 bucket name (uses temp bucket if not specified)
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            if not bucket_name:
                bucket_name = self.config.TEMP_BUCKET
            
            self.s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
            
            logger.info(f"Successfully deleted s3://{bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting S3 object: {e}")
            return False
    
    def copy_object(self, source_bucket: str, source_key: str, 
                   dest_key: str, dest_bucket: Optional[str] = None) -> bool:
        """
        Copy S3 object from source to destination
        
        Args:
            source_bucket: Source bucket name
            source_key: Source object key
            dest_key: Destination object key
            dest_bucket: Destination bucket name (uses output bucket if not specified)
            
        Returns:
            True if copy successful, False otherwise
        """
        try:
            if not dest_bucket:
                dest_bucket = self.config.OUTPUT_BUCKET
            
            copy_source = {'Bucket': source_bucket, 'Key': source_key}
            
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=dest_bucket,
                Key=dest_key
            )
            
            logger.info(f"Successfully copied s3://{source_bucket}/{source_key} to s3://{dest_bucket}/{dest_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error copying S3 object: {e}")
            return False
    
    def check_object_exists(self, s3_key: str, bucket_name: Optional[str] = None) -> bool:
        """
        Check if S3 object exists
        
        Args:
            s3_key: S3 object key to check
            bucket_name: S3 bucket name (uses input bucket if not specified)
            
        Returns:
            True if object exists, False otherwise
        """
        try:
            if not bucket_name:
                bucket_name = self.config.INPUT_BUCKET
            
            self.s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                return False
            else:
                logger.error(f"Error checking S3 object existence: {e}")
                return False
    
    def get_object_metadata(self, s3_key: str, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get S3 object metadata
        
        Args:
            s3_key: S3 object key
            bucket_name: S3 bucket name (uses input bucket if not specified)
            
        Returns:
            Object metadata dictionary or None if failed
        """
        try:
            if not bucket_name:
                bucket_name = self.config.INPUT_BUCKET
            
            response = self.s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            
            metadata = {
                'content_length': response.get('ContentLength'),
                'content_type': response.get('ContentType'),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag'),
                'metadata': response.get('Metadata', {})
            }
            
            return metadata
            
        except ClientError as e:
            logger.error(f"Error getting S3 object metadata: {e}")
            return None
    
    def create_multipart_upload(self, s3_key: str, content_type: str = 'application/octet-stream') -> Optional[str]:
        """
        Create multipart upload for large files
        
        Args:
            s3_key: S3 object key
            content_type: MIME content type
            
        Returns:
            Upload ID or None if failed
        """
        try:
            bucket_name = self.config.OUTPUT_BUCKET
            
            response = self.s3_client.create_multipart_upload(
                Bucket=bucket_name,
                Key=s3_key,
                ContentType=content_type
            )
            
            upload_id = response['UploadId']
            logger.info(f"Created multipart upload for s3://{bucket_name}/{s3_key}, UploadId: {upload_id}")
            
            return upload_id
            
        except ClientError as e:
            logger.error(f"Error creating multipart upload: {e}")
            return None
    
    def upload_part(self, s3_key: str, upload_id: str, part_number: int, 
                   data: bytes) -> Optional[Dict[str, Any]]:
        """
        Upload part for multipart upload
        
        Args:
            s3_key: S3 object key
            upload_id: Multipart upload ID
            part_number: Part number (1-based)
            data: Part data
            
        Returns:
            Part info dictionary or None if failed
        """
        try:
            bucket_name = self.config.OUTPUT_BUCKET
            
            response = self.s3_client.upload_part(
                Bucket=bucket_name,
                Key=s3_key,
                PartNumber=part_number,
                UploadId=upload_id,
                Body=data
            )
            
            part_info = {
                'ETag': response['ETag'],
                'PartNumber': part_number
            }
            
            logger.debug(f"Uploaded part {part_number} for s3://{bucket_name}/{s3_key}")
            return part_info
            
        except ClientError as e:
            logger.error(f"Error uploading part: {e}")
            return None
    
    def complete_multipart_upload(self, s3_key: str, upload_id: str, 
                                 parts: List[Dict[str, Any]]) -> bool:
        """
        Complete multipart upload
        
        Args:
            s3_key: S3 object key
            upload_id: Multipart upload ID
            parts: List of part info dictionaries
            
        Returns:
            True if completion successful, False otherwise
        """
        try:
            bucket_name = self.config.OUTPUT_BUCKET
            
            multipart_upload = {
                'Parts': parts
            }
            
            self.s3_client.complete_multipart_upload(
                Bucket=bucket_name,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload=multipart_upload
            )
            
            logger.info(f"Completed multipart upload for s3://{bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error completing multipart upload: {e}")
            return False
    
    def abort_multipart_upload(self, s3_key: str, upload_id: str) -> bool:
        """
        Abort multipart upload
        
        Args:
            s3_key: S3 object key
            upload_id: Multipart upload ID
            
        Returns:
            True if abort successful, False otherwise
        """
        try:
            bucket_name = self.config.OUTPUT_BUCKET
            
            self.s3_client.abort_multipart_upload(
                Bucket=bucket_name,
                Key=s3_key,
                UploadId=upload_id
            )
            
            logger.info(f"Aborted multipart upload for s3://{bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error aborting multipart upload: {e}")
            return False
