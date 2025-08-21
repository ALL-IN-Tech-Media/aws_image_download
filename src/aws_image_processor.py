"""
AWS-adapted version of image_concat.py for Lambda environment
Handles image downloading and collage creation with S3 storage
"""

import csv
import io
import time
import requests
from PIL import Image
# import numpy as np  # Removed for Lambda compatibility
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import datetime
import gc
import psutil
import os

from s3_utils import S3Utils
from config import Config

logger = logging.getLogger(__name__)

class AWSImageProcessor:
    """AWS Lambda optimized image processor"""
    
    def __init__(self, config: 'Config'):
        """
        Initialize AWS Image Processor
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.s3_utils = S3Utils(config)
        self.results = []
        
    def download_image_from_url(self, url: str, timeout: int = 30, max_retries: int = 3) -> Optional[Image.Image]:
        """
        Download image from URL and return PIL Image object with retry mechanism
        
        Args:
            url: Image URL to download
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        
        Returns:
            PIL Image object or None if failed
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=timeout, stream=True)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                if not content_type.startswith('image/'):
                    logger.warning(f"URL does not return image content: {url} (content-type: {content_type})")
                    return None
                
                # Load image from response content
                image_data = io.BytesIO(response.content)
                image = Image.open(image_data)
                
                # Convert to RGB if necessary (handle RGBA, P mode, etc.)
                if image.mode not in ('RGB', 'L'):
                    image = image.convert('RGB')
                
                # Validate image dimensions
                if image.width < 50 or image.height < 50:
                    logger.warning(f"Image too small ({image.width}x{image.height}): {url}")
                    return None
                
                logger.debug(f"Successfully downloaded image: {url} ({image.width}x{image.height})")
                return image
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                logger.warning(f"Error processing image from {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        
        logger.error(f"Failed to download image after {max_retries} attempts: {url}")
        return None

    def download_images_batch(self, urls: List[str], max_workers: int = 8, 
                             timeout: int = 30, max_retries: int = 3) -> List[Image.Image]:
        """
        Download multiple images concurrently using ThreadPoolExecutor
        
        Args:
            urls: List of image URLs to download
            max_workers: Maximum number of concurrent download threads
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts per URL
        
        Returns:
            List of successfully downloaded PIL Image objects
        """
        if not urls:
            logger.warning("No URLs provided for batch download")
            return []
        
        downloaded_images = []
        failed_count = 0
        
        logger.info(f"Starting batch download of {len(urls)} images with {max_workers} workers")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all download tasks
            future_to_url = {}
            for i, url in enumerate(urls):
                if url and url.strip():  # Skip empty URLs
                    future = executor.submit(self.download_image_from_url, url, timeout, max_retries)
                    future_to_url[future] = (url, i)
            
            # Process completed downloads
            for future in as_completed(future_to_url):
                url, index = future_to_url[future]
                try:
                    image = future.result()
                    if image:
                        downloaded_images.append(image)
                        logger.info(f"Downloaded image {len(downloaded_images)}/{len(future_to_url)}: {index+1}")
                    else:
                        failed_count += 1
                        logger.warning(f"Failed to download image {index+1}: {url[:100]}...")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Exception downloading image {index+1}: {e}")
        
        success_count = len(downloaded_images)
        total_attempted = len(future_to_url)
        
        logger.info(f"Batch download completed: {success_count}/{total_attempted} successful, {failed_count} failed")
        
        return downloaded_images

    def calculate_optimal_dimensions(self, images: List[Image.Image], 
                                   target_width: Optional[int] = None, 
                                   target_height: Optional[int] = None) -> Tuple[int, int]:
        """
        Calculate optimal dimensions for collage images
        
        Args:
            images: List of PIL Image objects
            target_width: Target width (if None, use average)
            target_height: Target height (if None, use average)
        
        Returns:
            Tuple of (width, height) for individual images in collage
        """
        if not images:
            return 300, 300  # Default size if no images
        
        if target_width and target_height:
            return target_width, target_height
        
        # Calculate statistics from available images
        widths = [img.width for img in images]
        heights = [img.height for img in images]
        
        if target_width:
            # Use target width, calculate proportional height
            avg_ratio = sum(h/w for w, h in zip(widths, heights)) / len(widths)
            return target_width, int(target_width * avg_ratio)
        
        if target_height:
            # Use target height, calculate proportional width
            avg_ratio = sum(w/h for w, h in zip(widths, heights)) / len(widths)
            return int(target_height * avg_ratio), target_height
        
        # Use average dimensions
        avg_width = int(sum(widths) / len(widths))
        avg_height = int(sum(heights) / len(heights))
        
        # Ensure reasonable minimum size
        min_size = 200
        avg_width = max(avg_width, min_size)
        avg_height = max(avg_height, min_size)
        
        # Ensure reasonable maximum size
        max_size = 800
        avg_width = min(avg_width, max_size)
        avg_height = min(avg_height, max_size)
        
        logger.info(f"Calculated optimal dimensions: {avg_width}x{avg_height} from {len(images)} images")
        
        return avg_width, avg_height

    def monitor_memory_usage(self) -> Dict[str, float]:
        """
        Monitor current memory usage
        
        Returns:
            Dictionary with memory statistics
        """
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,  # Resident Set Size in MB
            'vms_mb': memory_info.vms / 1024 / 1024,  # Virtual Memory Size in MB
            'percent': process.memory_percent()
        }

    def create_image_collage_s3(self, image_urls: List[str], s3_key: str, 
                               rows: int = 5, cols: int = 7,
                               target_width: Optional[int] = None, 
                               target_height: Optional[int] = None,
                               max_workers: int = 8, timeout: int = 30, 
                               max_retries: int = 3, quality: int = 95,
                               background_color: Tuple[int, int, int] = (255, 255, 255)) -> bool:
        """
        Create image collage from list of URLs and upload to S3
        
        Args:
            image_urls: List of image URLs to download and arrange
            s3_key: S3 key where collage will be saved
            rows: Number of rows in the grid
            cols: Number of columns in the grid
            target_width: Target width for individual images (None for auto)
            target_height: Target height for individual images (None for auto)
            max_workers: Maximum concurrent download threads
            timeout: Download timeout in seconds
            max_retries: Maximum retry attempts per image
            quality: JPEG quality (1-100)
            background_color: RGB background color for empty cells
        
        Returns:
            bool: True if collage was created successfully
        """
        try:
            logger.info(f"Creating {rows}x{cols} collage from {len(image_urls)} URLs")
            
            # Monitor memory before starting
            memory_before = self.monitor_memory_usage()
            logger.info(f"Memory before processing: {memory_before}")
            
            if not image_urls:
                logger.error("No image URLs provided")
                return False
            
            # Step 1: Download images
            logger.info("Downloading images...")
            images = self.download_images_batch(image_urls, max_workers, timeout, max_retries)
            
            if not images:
                logger.error("No images were successfully downloaded")
                return False
            
            logger.info(f"Successfully downloaded {len(images)} images")
            
            # Monitor memory after downloads
            memory_after_download = self.monitor_memory_usage()
            logger.info(f"Memory after downloads: {memory_after_download}")
            
            # Step 2: Calculate optimal dimensions
            img_width, img_height = self.calculate_optimal_dimensions(images, target_width, target_height)
            
            # Step 3: Create canvas
            canvas_width = img_width * cols
            canvas_height = img_height * rows
            canvas = Image.new('RGB', (canvas_width, canvas_height), background_color)
            
            logger.info(f"Created canvas: {canvas_width}x{canvas_height} pixels")
            
            # Step 4: Place images in grid
            total_cells = rows * cols
            images_to_place = min(len(images), total_cells)
            
            for i in range(images_to_place):
                try:
                    # Calculate grid position
                    row = i // cols
                    col = i % cols
                    x = col * img_width
                    y = row * img_height
                    
                    # Resize image to fit cell
                    img = images[i]
                    img_resized = img.resize((img_width, img_height), Image.Resampling.LANCZOS)
                    
                    # Paste image onto canvas
                    canvas.paste(img_resized, (x, y))
                    
                    logger.debug(f"Placed image {i+1}/{images_to_place} at position ({row}, {col})")
                    
                    # Free memory of processed image
                    img.close()
                    img_resized.close()
                    
                except Exception as e:
                    logger.warning(f"Error placing image {i+1}: {e}")
                    continue
            
            # Free memory of downloaded images
            for img in images:
                img.close()
            del images
            gc.collect()
            
            # Monitor memory after collage creation
            memory_after_collage = self.monitor_memory_usage()
            logger.info(f"Memory after collage creation: {memory_after_collage}")
            
            # Step 5: Save collage to S3
            collage_buffer = io.BytesIO()
            canvas.save(collage_buffer, 'JPEG', quality=quality, optimize=True)
            collage_buffer.seek(0)
            
            # Upload to S3
            success = self.s3_utils.upload_file_to_s3(
                file_buffer=collage_buffer,
                s3_key=s3_key,
                content_type='image/jpeg'
            )
            
            # Free canvas memory
            canvas.close()
            del canvas
            gc.collect()
            
            if success:
                logger.info(f"Successfully created and uploaded collage: {s3_key}")
                logger.info(f"Collage contains {images_to_place} images in {rows}x{cols} grid")
                return True
            else:
                logger.error(f"Failed to upload collage to S3: {s3_key}")
                return False
            
        except Exception as e:
            logger.error(f"Error creating collage: {e}", exc_info=True)
            return False

    def process_csv_data(self, csv_data: str, output_prefix: str = "", 
                        group_by_creator: bool = True, rows: int = 5, cols: int = 7,
                        max_images_per_creator: Optional[int] = None,
                        max_workers: int = 8, timeout: int = 30, max_retries: int = 3,
                        quality: int = 95) -> Dict[str, Any]:
        """
        Process CSV data and create collages grouped by creator or combined
        
        Args:
            csv_data: CSV data as string
            output_prefix: S3 key prefix for output files
            group_by_creator: If True, create separate collages per creator
            rows: Number of rows in each collage grid
            cols: Number of columns in each collage grid
            max_images_per_creator: Maximum images per creator (None for all)
            max_workers: Maximum concurrent download threads
            timeout: Download timeout in seconds
            max_retries: Maximum retry attempts per image
            quality: JPEG quality (1-100)
        
        Returns:
            Dict with processing statistics and results
        """
        try:
            logger.info(f"Processing CSV data with {len(csv_data)} characters")
            
            # Parse CSV data
            csv_reader = csv.DictReader(io.StringIO(csv_data))
            
            # Load data from CSV
            data_by_creator = {}
            total_urls = 0
            
            for row in csv_reader:
                creator_name = row.get('creator_name', 'unknown').strip()
                cover_url = row.get('cover_url', '').strip()
                created_at = row.get('created_at', '')
                
                if cover_url and not cover_url.startswith('ERROR:'):
                    if creator_name not in data_by_creator:
                        data_by_creator[creator_name] = []
                    
                    data_by_creator[creator_name].append({
                        'url': cover_url,
                        'created_at': created_at
                    })
                    total_urls += 1
            
            logger.info(f"Loaded {total_urls} URLs from {len(data_by_creator)} creators")
            
            if not data_by_creator:
                logger.error("No valid URLs found in CSV")
                return {"success": False, "error": "No valid URLs found"}
            
            results = {
                "success": True,
                "total_creators": len(data_by_creator),
                "total_urls": total_urls,
                "collages_created": [],
                "failed_creators": []
            }
            
            if group_by_creator:
                # Create separate collage for each creator
                for creator_name, creator_data in data_by_creator.items():
                    try:
                        logger.info(f"Processing creator: {creator_name} ({len(creator_data)} images)")
                        
                        # Limit images if specified
                        if max_images_per_creator and len(creator_data) > max_images_per_creator:
                            creator_data = creator_data[:max_images_per_creator]
                            logger.info(f"Limited to {max_images_per_creator} images for {creator_name}")
                        
                        # Extract URLs
                        urls = [item['url'] for item in creator_data]
                        
                        # Generate S3 key
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_creator_name = "".join(c for c in creator_name if c.isalnum() or c in (' ', '-', '_')).strip()
                        safe_creator_name = safe_creator_name.replace(' ', '_')
                        s3_key = f"{output_prefix}collages/{safe_creator_name}_collage_{timestamp}.jpg"
                        
                        # Create collage
                        success = self.create_image_collage_s3(
                            urls, s3_key, rows, cols,
                            max_workers=max_workers, timeout=timeout,
                            max_retries=max_retries, quality=quality
                        )
                        
                        if success:
                            s3_url = self.s3_utils.generate_presigned_url(s3_key)
                            results["collages_created"].append({
                                "creator": creator_name,
                                "s3_key": s3_key,
                                "s3_url": s3_url,
                                "image_count": len(urls)
                            })
                            logger.info(f"✓ Created collage for {creator_name}: {s3_key}")
                        else:
                            results["failed_creators"].append(creator_name)
                            logger.error(f"✗ Failed to create collage for {creator_name}")
                    
                    except Exception as e:
                        logger.error(f"Error processing creator {creator_name}: {e}")
                        results["failed_creators"].append(creator_name)
            
            else:
                # Create single combined collage
                try:
                    logger.info("Creating combined collage from all creators")
                    
                    # Collect all URLs
                    all_urls = []
                    for creator_data in data_by_creator.values():
                        for item in creator_data:
                            all_urls.append(item['url'])
                    
                    # Limit total images if needed
                    max_total = rows * cols * 3  # Allow some extra for failed downloads
                    if len(all_urls) > max_total:
                        all_urls = all_urls[:max_total]
                        logger.info(f"Limited to {max_total} total images for combined collage")
                    
                    # Generate S3 key
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    s3_key = f"{output_prefix}collages/combined_collage_{timestamp}.jpg"
                    
                    # Create collage
                    success = self.create_image_collage_s3(
                        all_urls, s3_key, rows, cols,
                        max_workers=max_workers, timeout=timeout,
                        max_retries=max_retries, quality=quality
                    )
                    
                    if success:
                        s3_url = self.s3_utils.generate_presigned_url(s3_key)
                        results["collages_created"].append({
                            "creator": "combined",
                            "s3_key": s3_key,
                            "s3_url": s3_url,
                            "image_count": len(all_urls)
                        })
                        logger.info(f"✓ Created combined collage: {s3_key}")
                    else:
                        logger.error("✗ Failed to create combined collage")
                
                except Exception as e:
                    logger.error(f"Error creating combined collage: {e}")
            
            # Summary
            logger.info(f"Processing complete: {len(results['collages_created'])} collages created, {len(results['failed_creators'])} failed")
            
            return results
            
        except Exception as e:
            logger.error(f"Error processing CSV: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
