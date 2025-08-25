import csv
import os
import time
import requests
from PIL import Image
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from io import BytesIO
import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_image_from_url(url: str, timeout: int = 30, max_retries: int = 3) -> Optional[Image.Image]:
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
            image_data = BytesIO(response.content)
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

def download_images_batch(urls: List[str], max_workers: int = 8, timeout: int = 30, max_retries: int = 3) -> Tuple[List[Image.Image], float]:
    """
    Download multiple images concurrently using ThreadPoolExecutor
    
    Args:
        urls: List of image URLs to download
        max_workers: Maximum number of concurrent download threads
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts per URL
    
    Returns:
        Tuple of (List of successfully downloaded PIL Image objects, download_time_seconds)
    """
    if not urls:
        logger.warning("No URLs provided for batch download")
        return [], 0.0
    
    download_start_time = time.time()
    downloaded_images = []
    failed_count = 0
    
    logger.info(f"Starting batch download of {len(urls)} images with {max_workers} workers")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_url = {}
        for i, url in enumerate(urls):
            if url and url.strip():  # Skip empty URLs
                future = executor.submit(download_image_from_url, url, timeout, max_retries)
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
    download_time = time.time() - download_start_time
    
    logger.info(f"Batch download completed: {success_count}/{total_attempted} successful, {failed_count} failed in {download_time:.2f}s")
    
    return downloaded_images, download_time

def calculate_optimal_dimensions(images: List[Image.Image], target_width: Optional[int] = None, target_height: Optional[int] = None) -> Tuple[int, int]:
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
        avg_ratio = np.mean([h/w for w, h in zip(widths, heights)])
        return target_width, int(target_width * avg_ratio)
    
    if target_height:
        # Use target height, calculate proportional width
        avg_ratio = np.mean([w/h for w, h in zip(widths, heights)])
        return int(target_height * avg_ratio), target_height
    
    # Use average dimensions
    avg_width = int(np.mean(widths))
    avg_height = int(np.mean(heights))
    
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

def create_image_collage(image_urls: List[str], output_path: str, rows: int = 5, cols: int = 7, 
                        target_width: Optional[int] = None, target_height: Optional[int] = None,
                        max_workers: int = 8, timeout: int = 30, max_retries: int = 3,
                        quality: int = 95, background_color: Tuple[int, int, int] = (255, 255, 255)) -> Tuple[bool, Dict[str, float]]:
    """
    Create image collage from list of URLs
    
    Args:
        image_urls: List of image URLs to download and arrange
        output_path: Path where collage will be saved
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
        Tuple of (success: bool, timing_info: Dict[str, float])
    """
    timing_info = {}
    total_start_time = time.time()
    
    try:
        logger.info(f"Creating {rows}x{cols} collage from {len(image_urls)} URLs")
        
        if not image_urls:
            logger.error("No image URLs provided")
            return False, {}
        
        # Step 1: Download images
        logger.info("Downloading images...")
        images, download_time = download_images_batch(image_urls, max_workers, timeout, max_retries)
        timing_info['download_time'] = download_time
        
        if not images:
            logger.error("No images were successfully downloaded")
            return False, timing_info
        
        logger.info(f"Successfully downloaded {len(images)} images")
        
        # Step 2: Calculate optimal dimensions
        dimensions_start_time = time.time()
        img_width, img_height = calculate_optimal_dimensions(images, target_width, target_height)
        timing_info['dimensions_time'] = time.time() - dimensions_start_time
        
        # Step 3: Create canvas
        canvas_start_time = time.time()
        canvas_width = img_width * cols
        canvas_height = img_height * rows
        canvas = Image.new('RGB', (canvas_width, canvas_height), background_color)
        timing_info['canvas_creation_time'] = time.time() - canvas_start_time
        
        logger.info(f"Created canvas: {canvas_width}x{canvas_height} pixels")
        
        # Step 4: Place images in grid
        placement_start_time = time.time()
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
                
            except Exception as e:
                logger.warning(f"Error placing image {i+1}: {e}")
                continue
        
        timing_info['placement_time'] = time.time() - placement_start_time
        
        # Step 5: Save collage
        save_start_time = time.time()
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save with specified quality
        canvas.save(output_path, 'JPEG', quality=quality, optimize=True)
        timing_info['save_time'] = time.time() - save_start_time
        
        # Calculate total time
        timing_info['total_time'] = time.time() - total_start_time
        
        logger.info(f"Successfully created collage: {output_path}")
        logger.info(f"Collage contains {images_to_place} images in {rows}x{cols} grid")
        logger.info(f"Timing - Download: {timing_info['download_time']:.2f}s, "
                   f"Dimensions: {timing_info['dimensions_time']:.3f}s, "
                   f"Canvas: {timing_info['canvas_creation_time']:.3f}s, "
                   f"Placement: {timing_info['placement_time']:.2f}s, "
                   f"Save: {timing_info['save_time']:.2f}s, "
                   f"Total: {timing_info['total_time']:.2f}s")
        
        return True, timing_info
        
    except Exception as e:
        logger.error(f"Error creating collage: {e}")
        return False, timing_info

def process_csv_to_collages(csv_path: str, output_dir: str, group_by_creator: bool = True,
                           rows: int = 5, cols: int = 7, max_images_per_creator: Optional[int] = None,
                           max_workers: int = 8, timeout: int = 30, max_retries: int = 3,
                           quality: int = 95) -> Dict[str, Any]:
    """
    Process CSV file and create collages grouped by creator or combined
    
    Args:
        csv_path: Path to CSV file with cover URLs
        output_dir: Output directory for collages
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
    total_start_time = time.time()
    
    try:
        logger.info(f"Processing CSV file: {csv_path}")
        
        # Read CSV file
        if not os.path.exists(csv_path):
            logger.error(f"CSV file not found: {csv_path}")
            return {"success": False, "error": "CSV file not found"}
        
        # Load data from CSV
        csv_start_time = time.time()
        data_by_creator = {}
        total_urls = 0
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                creator_name = row.get('creator_name', 'unknown').strip()
                cover_url = row.get('cover_url', '').strip()
                updated_at = row.get('updated_at', '')
                
                if cover_url and not cover_url.startswith('ERROR:'):
                    if creator_name not in data_by_creator:
                        data_by_creator[creator_name] = []
                    
                    data_by_creator[creator_name].append({
                        'url': cover_url,
                        'updated_at': updated_at
                    })
                    total_urls += 1
        
        csv_time = time.time() - csv_start_time
        logger.info(f"Loaded {total_urls} URLs from {len(data_by_creator)} creators in {csv_time:.2f}s")
        
        if not data_by_creator:
            logger.error("No valid URLs found in CSV")
            return {"success": False, "error": "No valid URLs found"}
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        results = {
            "success": True,
            "total_creators": len(data_by_creator),
            "total_urls": total_urls,
            "collages_created": [],
            "failed_creators": [],
            "timing": {
                "csv_processing_time": csv_time,
                "collage_timings": []
            }
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
                    
                    # Generate output filename
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_creator_name = "".join(c for c in creator_name if c.isalnum() or c in (' ', '-', '_')).strip()
                    safe_creator_name = safe_creator_name.replace(' ', '_')
                    output_filename = f"{safe_creator_name}_collage_{timestamp}.jpg"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    # Create collage
                    success, collage_timing = create_image_collage(
                        urls, output_path, rows, cols,
                        max_workers=max_workers, timeout=timeout,
                        max_retries=max_retries, quality=quality
                    )
                    
                    if success:
                        collage_info = {
                            "creator": creator_name,
                            "path": output_path,
                            "image_count": len(urls),
                            "filename": output_filename,
                            "timing": collage_timing
                        }
                        results["collages_created"].append(collage_info)
                        results["timing"]["collage_timings"].append({
                            "creator": creator_name,
                            **collage_timing
                        })
                        logger.info(f"✓ Created collage for {creator_name}: {output_filename}")
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
                
                # Generate output filename
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"combined_collage_{timestamp}.jpg"
                output_path = os.path.join(output_dir, output_filename)
                
                # Create collage
                success, collage_timing = create_image_collage(
                    all_urls, output_path, rows, cols,
                    max_workers=max_workers, timeout=timeout,
                    max_retries=max_retries, quality=quality
                )
                
                if success:
                    collage_info = {
                        "creator": "combined",
                        "path": output_path,
                        "image_count": len(all_urls),
                        "filename": output_filename,
                        "timing": collage_timing
                    }
                    results["collages_created"].append(collage_info)
                    results["timing"]["collage_timings"].append({
                        "creator": "combined",
                        **collage_timing
                    })
                    logger.info(f"✓ Created combined collage: {output_filename}")
                else:
                    logger.error("✗ Failed to create combined collage")
            
            except Exception as e:
                logger.error(f"Error creating combined collage: {e}")
        
        # Summary
        total_processing_time = time.time() - total_start_time
        results["timing"]["total_processing_time"] = total_processing_time
        
        logger.info(f"Processing complete: {len(results['collages_created'])} collages created, {len(results['failed_creators'])} failed")
        logger.info(f"Total processing time: {total_processing_time:.2f}s")
        
        # Log timing summary
        if results["timing"]["collage_timings"]:
            total_download_time = sum(ct.get('download_time', 0) for ct in results["timing"]["collage_timings"])
            total_placement_time = sum(ct.get('placement_time', 0) for ct in results["timing"]["collage_timings"])
            total_save_time = sum(ct.get('save_time', 0) for ct in results["timing"]["collage_timings"])
            
            logger.info(f"Timing Summary - CSV: {results['timing']['csv_processing_time']:.2f}s, "
                       f"Downloads: {total_download_time:.2f}s, "
                       f"Placement: {total_placement_time:.2f}s, "
                       f"Saving: {total_save_time:.2f}s")
        
        return results
        
    except Exception as e:
        logger.error(f"Error processing CSV: {e}")
        return {"success": False, "error": str(e)}

def main():
    """
    Main function with example usage scenarios
    """
    print("=== TikTok Image Collage Creator ===")
    print()
    
    # Configuration
    output_dir = "/home/geshuhang/aws_image_download/collages"
    
    # Example 1: Process CSV from get_urls.py and create collages per creator
    print("Example 1: Creating collages per creator from CSV...")
    
    # Look for the most recent CSV file
    csv_files = []
    for file in os.listdir("/home/geshuhang/aws_image_download"):
        if file.startswith("cover_urls_") and file.endswith(".csv"):
            csv_files.append(file)
    
    if csv_files:
        # Use the most recent CSV file
        csv_files.sort()
        latest_csv = csv_files[-1]
        csv_path = f"/home/geshuhang/aws_image_download/{latest_csv}"
        
        print(f"Using CSV file: {latest_csv}")
        
        # Create collages grouped by creator
        results = process_csv_to_collages(
            csv_path=csv_path,
            output_dir=output_dir,
            group_by_creator=True,
            rows=5,
            cols=7,
            max_images_per_creator=35,  # Limit to 35 images per creator (5x7 grid)
            max_workers=8,
            timeout=30,
            max_retries=3,
            quality=95
        )
        
        if results["success"]:
            print(f"✓ Successfully processed {results['total_creators']} creators")
            print(f"✓ Created {len(results['collages_created'])} collages")
            print(f"✓ Total URLs processed: {results['total_urls']}")
            
            # Display timing information
            if "timing" in results:
                timing = results["timing"]
                print(f"\n⏱️  Timing Summary:")
                print(f"  - CSV Processing: {timing.get('csv_processing_time', 0):.2f}s")
                print(f"  - Total Processing: {timing.get('total_processing_time', 0):.2f}s")
                
                if timing.get("collage_timings"):
                    total_download = sum(ct.get('download_time', 0) for ct in timing["collage_timings"])
                    total_placement = sum(ct.get('placement_time', 0) for ct in timing["collage_timings"])
                    total_save = sum(ct.get('save_time', 0) for ct in timing["collage_timings"])
                    
                    print(f"  - Total Download Time: {total_download:.2f}s")
                    print(f"  - Total Placement Time: {total_placement:.2f}s")
                    print(f"  - Total Save Time: {total_save:.2f}s")
                    
                    avg_per_collage = timing.get('total_processing_time', 0) / len(results['collages_created']) if results['collages_created'] else 0
                    print(f"  - Average per Collage: {avg_per_collage:.2f}s")
            
            if results["collages_created"]:
                print("\nCreated collages:")
                for collage in results["collages_created"]:
                    timing_info = ""
                    if "timing" in collage:
                        timing_info = f" (Total: {collage['timing'].get('total_time', 0):.1f}s)"
                    print(f"  - {collage['creator']}: {collage['filename']} ({collage['image_count']} images){timing_info}")
            
            if results["failed_creators"]:
                print(f"\n⚠ Failed creators: {', '.join(results['failed_creators'])}")
        else:
            print(f"✗ Processing failed: {results.get('error', 'Unknown error')}")
    else:
        print("No CSV files found. Please run get_urls.py first to extract URLs.")
    
    print()
    
    # # Example 2: Create a single combined collage
    # print("Example 2: Creating single combined collage...")
    
    # if csv_files:
    #     csv_path = f"/home/geshuhang/aws_image_download/{latest_csv}"
        
    #     results = process_csv_to_collages(
    #         csv_path=csv_path,
    #         output_dir=output_dir,
    #         group_by_creator=False,  # Combined collage
    #         rows=7,
    #         cols=10,  # Larger grid for combined
    #         max_workers=8,
    #         timeout=30,
    #         max_retries=3,
    #         quality=95
    #     )
        
    #     if results["success"] and results["collages_created"]:
    #         collage = results["collages_created"][0]
    #         print(f"✓ Created combined collage: {collage['filename']} ({collage['image_count']} images)")
    #     else:
    #         print(f"✗ Failed to create combined collage: {results.get('error', 'Unknown error')}")
    
    # print()
    
    # # Example 3: Direct URL collage (for testing)
    # print("Example 3: Creating test collage from sample URLs...")
    
    # # Sample TikTok cover URLs for testing (you can replace these with actual URLs)
    # sample_urls = [
    #     # Add some sample URLs here for testing if needed
    #     # These would be actual TikTok cover URLs from your database
    # ]
    
    # if sample_urls:
    #     test_output_path = os.path.join(output_dir, "test_collage.jpg")
    #     success = create_image_collage(
    #         image_urls=sample_urls,
    #         output_path=test_output_path,
    #         rows=3,
    #         cols=3,
    #         max_workers=4,
    #         timeout=30,
    #         max_retries=2,
    #         quality=90
    #     )
        
    #     if success:
    #         print(f"✓ Created test collage: test_collage.jpg")
    #     else:
    #         print("✗ Failed to create test collage")
    # else:
    #     print("No sample URLs provided for testing")
    
    # print()
    # print("=== Processing Complete ===")
    # print(f"Output directory: {output_dir}")

if __name__ == "__main__":
    main()