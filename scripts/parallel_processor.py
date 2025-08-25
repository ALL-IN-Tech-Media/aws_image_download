#!/usr/bin/env python3
"""
Parallel CSV processor for maximum speed TikTok image processing.
Splits large CSV files into optimal batches for concurrent Lambda processing.
"""

import csv
import json
import time
import boto3
import sys
import os
from datetime import datetime
from typing import List, Dict, Tuple
import argparse
import logging

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from creator_registry import CreatorBatchManager
# Configure logging
# get absolute path of the folder where this Python file lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# point to the "result" folder inside the same directory
LOG_FILE = os.path.join(BASE_DIR, "logs", "app.log")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename=LOG_FILE,         # log file name
                    filemode="w")
logger = logging.getLogger(__name__)
class ParallelProcessor:
    def __init__(self, region='us-east-2', enable_deduplication=True):
        self.s3 = boto3.client('s3', region_name=region)
        self.sqs = boto3.client('sqs', region_name=region)
        self.region = region
        self.input_bucket = 'tiktok-image-input'
        self.queue_url = f"https://sqs.{region}.amazonaws.com/624433616538/tiktok-image-processing-queue"
        self.enable_deduplication = enable_deduplication
        
        # Initialize creator batch manager for deduplication
        if self.enable_deduplication:
            self.batch_manager = CreatorBatchManager()
            logger.info("Deduplication enabled - using CreatorBatchManager")
        else:
            self.batch_manager = None
            logger.info("Deduplication disabled - using legacy batching")
        
    def analyze_csv(self, csv_file: str) -> Dict[str, int]:
        """Analyze CSV to understand creator distribution."""
        creators = {}
        total_images = 0
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['cover_url'].strip():  # Only count rows with URLs
                    creator = row['creator_name']
                    creators[creator] = creators.get(creator, 0) + 1
                    total_images += 1
        
        return creators, total_images
    
    def create_balanced_batches(self, csv_file: str, target_batch_size: int = 100) -> List[List[Dict]]:
        """Create balanced batches for parallel processing with deduplication support."""
        creators, total_images = self.analyze_csv(csv_file)
        
        print(f"📊 Analysis: {len(creators)} creators, {total_images} images")
        
        # Read all rows and group by creator
        creator_groups = {}
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['cover_url'].strip():
                    creator = row['creator_name']
                    if creator not in creator_groups:
                        creator_groups[creator] = []
                    creator_groups[creator].append(row)
        
        if self.enable_deduplication and self.batch_manager:
            # Use creator-centric batching to prevent duplicates
            print("🔧 Using creator-centric batching for deduplication")
            
            # Convert to URL format for batch manager
            creators_data = {}
            for creator, rows in creator_groups.items():
                creators_data[creator] = [row['cover_url'] for row in rows]
            
            # Create balanced creator batches
            creator_batches = self.batch_manager.create_balanced_creator_batches(
                creators_data, target_batch_size
            )
            
            # Validate no duplicate creators
            validation = self.batch_manager.validate_no_duplicate_creators(creator_batches)
            if not validation['valid']:
                logger.error(f"Batch validation failed: {validation}")
                raise ValueError(f"Duplicate creators found: {validation['duplicate_creators']}")
            
            # Convert back to row format
            batches = []
            for creator_batch in creator_batches:
                batch_rows = []
                for creator, urls in creator_batch.items():
                    # Get original rows for this creator
                    creator_rows = creator_groups[creator]
                    batch_rows.extend(creator_rows)
                batches.append(batch_rows)
            
            print(f"✅ Created {len(batches)} deduplication-safe batches")
            
        else:
            # Use legacy batching (may create duplicates)
            print("⚠️  Using legacy batching - duplicates possible")
            
            batches = []
            current_batch = []
            current_size = 0
            
            # Sort creators by size (largest first for better balancing)
            sorted_creators = sorted(creator_groups.items(), key=lambda x: len(x[1]), reverse=True)
            
            for creator, rows in sorted_creators:
                if current_size + len(rows) > target_batch_size and current_batch:
                    # Start new batch
                    batches.append(current_batch)
                    current_batch = []
                    current_size = 0
                
                current_batch.extend(rows)
                current_size += len(rows)
            
            # Add final batch
            if current_batch:
                batches.append(current_batch)
        
        # Log batch statistics
        self._log_final_batch_stats(batches, target_batch_size)
        
        return batches
    
    def create_csv_content(self, rows: List[Dict]) -> str:
        """Convert rows back to CSV content."""
        if not rows:
            return ""
        
        # Create CSV content
        csv_lines = ['creator_name,cover_url,updated_at']
        
        for row in rows:
            csv_lines.append(f"{row['creator_name']},{row['cover_url']},{row['updated_at']}")
        
        return '\n'.join(csv_lines)
    
    def process_parallel_s3(self, csv_file: str, batch_size: int = 100) -> List[str]:
        """Process via parallel S3 uploads (fastest method)."""
        batches = self.create_balanced_batches(csv_file, batch_size)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        print(f"🚀 Creating {len(batches)} parallel batches...")
        
        uploaded_files = []
        start_time = time.time()
        
        for i, batch in enumerate(batches):
            batch_name = f"{timestamp}/parallel_batch_{i+1:02d}.csv"
            csv_content = self.create_csv_content(batch)
            
            # Upload to S3 (triggers Lambda automatically)
            self.s3.put_object(
                Bucket=self.input_bucket,
                Key=f'csv-files/version1/{batch_name}',
                Body=csv_content
            )
            
            uploaded_files.append(batch_name)
            print(f"✅ Batch {i+1}/{len(batches)}: {len(batch)} images → {batch_name}")
        
        upload_time = time.time() - start_time
        print(f"⚡ All batches uploaded in {upload_time:.2f} seconds")
        print(f"🎯 Expected processing time: ~{max(len(batch) for batch in batches) / 13:.1f} seconds")
        
        return uploaded_files
    
    def process_parallel_sqs(self, csv_file: str, batch_size: int = 100) -> List[str]:
        """Process via parallel SQS messages (more control)."""
        batches = self.create_balanced_batches(csv_file, batch_size)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        print(f"🚀 Sending {len(batches)} parallel SQS messages...")
        
        message_ids = []
        start_time = time.time()
        
        for i, batch in enumerate(batches):
            csv_content = self.create_csv_content(batch)
            
            message = {
                "processing_type": "csv_data",
                "csv_data": csv_content,
                "processing_config": {
                    "rows": 5,
                    "cols": 7,
                    "quality": 95,
                    "max_workers": 8,
                    "timeout": 30,
                    "max_retries": 3
                },
                "output_prefix": f"parallel_sqs_{timestamp}/"
            }
            
            response = self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message)
            )
            logger.info(f'response for batch{i}: {response}')
            message_ids.append(response['MessageId'])
            print(f"✅ Batch {i+1}/{len(batches)}: {len(batch)} images → SQS message sent")
        
        send_time = time.time() - start_time
        print(f"⚡ All messages sent in {send_time:.2f} seconds")
        print(f"🎯 Expected processing time: ~{max(len(batch) for batch in batches) / 13:.1f} seconds")
        
        return message_ids
    
    def _log_final_batch_stats(self, batches: List[List[Dict]], target_batch_size: int):
        """Log final statistics about created batches."""
        if not batches:
            print("⚠️  No batches created")
            return
        
        batch_sizes = [len(batch) for batch in batches]
        total_images = sum(batch_sizes)
        avg_batch_size = total_images / len(batches)
        
        print(f"📈 Final Batch Statistics:")
        print(f"   Total batches: {len(batches)}")
        print(f"   Total images: {total_images}")
        print(f"   Average batch size: {avg_batch_size:.1f}")
        print(f"   Min/Max batch size: {min(batch_sizes)}/{max(batch_sizes)}")
        print(f"   Target batch size: {target_batch_size}")
        
        # Check for batch balance
        size_variance = max(batch_sizes) - min(batch_sizes)
        if size_variance > target_batch_size * 0.5:
            print(f"⚠️  High batch size variance: {size_variance}")
        else:
            print(f"✅ Good batch balance (variance: {size_variance})")
    
    def monitor_processing(self, batch_count: int, method: str = "s3"):
        """Monitor parallel processing completion."""
        print(f"\n📊 Monitoring {batch_count} parallel {method.upper()} processes...")
        print("💡 Tip: Each batch runs in a separate Lambda instance!")
        
        # Monitor for completion
        import subprocess
        
        monitor_cmd = f"aws logs tail /aws/lambda/image-collage-processor --since 2m --region {self.region}"
        print(f"\n🔍 To monitor in real-time, run:")
        print(f"   {monitor_cmd}")
        
        print(f"\n📂 Results will be in:")
        if method == "s3":
            print(f"   s3://tiktok-image-output/s3-trigger/csv-files/")
        else:
            print(f"   s3://tiktok-image-output/sqs-trigger/parallel_sqs_*/")

def main():
    parser = argparse.ArgumentParser(description='Parallel TikTok image processor with deduplication')
    parser.add_argument('csv_file', help='CSV file to process')
    parser.add_argument('--method', choices=['s3', 'sqs'], default='s3', 
                       help='Processing method (s3=automatic, sqs=manual)')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Images per batch (default: 100)')
    parser.add_argument('--region', default='us-east-2',
                       help='AWS region (default: us-east-2)')
    parser.add_argument('--disable-deduplication', action='store_true',
                       help='Disable deduplication (may create duplicate collages)')
    
    args = parser.parse_args()
    
    enable_deduplication = not args.disable_deduplication
    processor = ParallelProcessor(region=args.region, enable_deduplication=enable_deduplication)
    
    print("🚀 PARALLEL PROCESSING STARTED")
    print("=" * 50)
    
    if enable_deduplication:
        print("🔒 DEDUPLICATION ENABLED - No duplicate collages will be created")
    else:
        print("⚠️  DEDUPLICATION DISABLED - Duplicate collages may be created")
    
    if args.method == 's3':
        uploaded_files = processor.process_parallel_s3(args.csv_file, args.batch_size)
        processor.monitor_processing(len(uploaded_files), 's3')
    else:
        message_ids = processor.process_parallel_sqs(args.csv_file, args.batch_size)
        processor.monitor_processing(len(message_ids), 'sqs')

if __name__ == "__main__":
    main()
