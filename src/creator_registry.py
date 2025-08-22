"""
Creator registry module for hash-based batch assignment
Ensures each creator appears in only one batch to prevent duplicates
"""

import hashlib
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)

class CreatorBatchManager:
    """Manages creator-to-batch assignments using deterministic hashing"""
    
    def __init__(self, hash_algorithm: str = 'sha256'):
        """
        Initialize creator batch manager
        
        Args:
            hash_algorithm: Hash algorithm for deterministic assignment
        """
        self.hash_algorithm = hash_algorithm.lower()
        self.creator_assignments: Dict[str, int] = {}
        self.batch_creators: Dict[int, List[str]] = defaultdict(list)
        self.batch_sizes: Dict[int, int] = defaultdict(int)
        
        # Validate algorithm
        if self.hash_algorithm not in ['sha256', 'md5', 'sha1']:
            raise ValueError(f"Unsupported hash algorithm: {hash_algorithm}")
        
        logger.info(f"CreatorBatchManager initialized with {hash_algorithm} algorithm")
    
    def _hash_creator_name(self, creator_name: str) -> int:
        """
        Generate deterministic hash for creator name
        
        Args:
            creator_name: Name of the creator
            
        Returns:
            Integer hash value
        """
        # Normalize creator name
        normalized_name = creator_name.strip().lower()
        
        # Generate hash
        hash_func = getattr(hashlib, self.hash_algorithm)
        hash_bytes = hash_func(normalized_name.encode('utf-8')).digest()
        
        # Convert to integer
        hash_int = int.from_bytes(hash_bytes[:4], byteorder='big')
        
        return hash_int
    
    def assign_creator_to_batch(self, creator_name: str, 
                              creator_image_count: int,
                              total_batches: int) -> int:
        """
        Assign creator to batch using deterministic hash-based assignment
        
        Args:
            creator_name: Name of the creator
            creator_image_count: Number of images for this creator
            total_batches: Total number of batches available
            
        Returns:
            Batch number (0-based) assigned to creator
        """
        try:
            # Check if creator already assigned
            if creator_name in self.creator_assignments:
                return self.creator_assignments[creator_name]
            
            # Generate deterministic batch assignment
            creator_hash = self._hash_creator_name(creator_name)
            batch_id = creator_hash % total_batches
            
            # Record assignment
            self.creator_assignments[creator_name] = batch_id
            self.batch_creators[batch_id].append(creator_name)
            self.batch_sizes[batch_id] += creator_image_count
            
            logger.debug(f"Assigned creator {creator_name} to batch {batch_id} "
                        f"({creator_image_count} images)")
            
            return batch_id
            
        except Exception as e:
            logger.error(f"Error assigning creator {creator_name} to batch: {e}")
            raise
    
    def create_balanced_creator_batches(self, creators_data: Dict[str, List[str]], 
                                      target_batch_size: int = 100) -> List[Dict[str, List[str]]]:
        """
        Create balanced batches ensuring each creator appears in only one batch
        
        Args:
            creators_data: Dictionary mapping creator names to their image URLs
            target_batch_size: Target number of images per batch
            
        Returns:
            List of batch dictionaries, each containing creator data
        """
        try:
            if not creators_data:
                logger.warning("No creator data provided for batching")
                return []
            
            # Calculate total images and optimal batch count
            total_images = sum(len(urls) for urls in creators_data.values())
            estimated_batches = max(1, (total_images + target_batch_size - 1) // target_batch_size)
            
            logger.info(f"Creating balanced batches: {len(creators_data)} creators, "
                       f"{total_images} images, target {estimated_batches} batches")
            
            # Sort creators by image count (largest first for better balancing)
            sorted_creators = sorted(
                creators_data.items(), 
                key=lambda x: len(x[1]), 
                reverse=True
            )
            
            # Initialize batches
            batches: List[Dict[str, List[str]]] = []
            batch_image_counts: List[int] = []
            
            # Assign each creator to a batch
            for creator_name, image_urls in sorted_creators:
                image_count = len(image_urls)
                
                # Find the batch with the least images (for balancing)
                if not batches:
                    # Create first batch
                    batches.append({creator_name: image_urls})
                    batch_image_counts.append(image_count)
                else:
                    # Use hash-based assignment as primary method
                    preferred_batch_id = self.assign_creator_to_batch(
                        creator_name, image_count, len(batches) + 1
                    )
                    
                    # Ensure the preferred batch exists
                    while len(batches) <= preferred_batch_id:
                        batches.append({})
                        batch_image_counts.append(0)
                    
                    # Check if preferred batch would exceed target size significantly
                    current_batch_size = batch_image_counts[preferred_batch_id]
                    
                    if current_batch_size + image_count > target_batch_size * 1.5:
                        # Find alternative batch or create new one
                        best_batch_id = self._find_best_alternative_batch(
                            batches, batch_image_counts, image_count, target_batch_size
                        )
                        
                        if best_batch_id is None:
                            # Create new batch
                            batches.append({creator_name: image_urls})
                            batch_image_counts.append(image_count)
                            # Update assignment record
                            self.creator_assignments[creator_name] = len(batches) - 1
                            self.batch_creators[len(batches) - 1] = [creator_name]
                            self.batch_sizes[len(batches) - 1] = image_count
                        else:
                            # Use alternative batch
                            batches[best_batch_id][creator_name] = image_urls
                            batch_image_counts[best_batch_id] += image_count
                            # Update assignment record
                            self.creator_assignments[creator_name] = best_batch_id
                            self.batch_creators[best_batch_id].append(creator_name)
                            self.batch_sizes[best_batch_id] += image_count
                    else:
                        # Use preferred batch
                        batches[preferred_batch_id][creator_name] = image_urls
                        batch_image_counts[preferred_batch_id] += image_count
            
            # Remove empty batches
            final_batches = [batch for batch in batches if batch]
            
            # Log batch statistics
            self._log_batch_statistics(final_batches, target_batch_size)
            
            return final_batches
            
        except Exception as e:
            logger.error(f"Error creating balanced creator batches: {e}")
            raise
    
    def _find_best_alternative_batch(self, batches: List[Dict[str, List[str]]], 
                                   batch_image_counts: List[int],
                                   creator_image_count: int,
                                   target_batch_size: int) -> Optional[int]:
        """
        Find the best alternative batch for a creator
        
        Args:
            batches: Current list of batches
            batch_image_counts: Current image counts per batch
            creator_image_count: Number of images for the creator
            target_batch_size: Target batch size
            
        Returns:
            Best batch ID or None if new batch should be created
        """
        best_batch_id = None
        best_score = float('inf')
        
        for batch_id, current_size in enumerate(batch_image_counts):
            new_size = current_size + creator_image_count
            
            # Skip if would exceed reasonable limit
            if new_size > target_batch_size * 2:
                continue
            
            # Calculate score (prefer batches closer to target size)
            if new_size <= target_batch_size:
                score = target_batch_size - new_size  # Prefer fuller batches
            else:
                score = new_size - target_batch_size  # Penalize oversized batches
            
            if score < best_score:
                best_score = score
                best_batch_id = batch_id
        
        return best_batch_id
    
    def _log_batch_statistics(self, batches: List[Dict[str, List[str]]], 
                            target_batch_size: int):
        """
        Log statistics about created batches
        
        Args:
            batches: List of created batches
            target_batch_size: Target batch size
        """
        if not batches:
            logger.warning("No batches created")
            return
        
        batch_sizes = []
        total_creators = 0
        total_images = 0
        
        for i, batch in enumerate(batches):
            batch_image_count = sum(len(urls) for urls in batch.values())
            batch_creator_count = len(batch)
            
            batch_sizes.append(batch_image_count)
            total_creators += batch_creator_count
            total_images += batch_image_count
            
            logger.info(f"Batch {i+1}: {batch_creator_count} creators, "
                       f"{batch_image_count} images")
        
        # Calculate statistics
        avg_batch_size = total_images / len(batches) if batches else 0
        min_batch_size = min(batch_sizes) if batch_sizes else 0
        max_batch_size = max(batch_sizes) if batch_sizes else 0
        
        # Calculate balance score (lower is better)
        balance_score = (max_batch_size - min_batch_size) / avg_batch_size if avg_batch_size > 0 else 0
        
        logger.info(f"Batch Statistics:")
        logger.info(f"  Total batches: {len(batches)}")
        logger.info(f"  Total creators: {total_creators}")
        logger.info(f"  Total images: {total_images}")
        logger.info(f"  Average batch size: {avg_batch_size:.1f}")
        logger.info(f"  Min/Max batch size: {min_batch_size}/{max_batch_size}")
        logger.info(f"  Target batch size: {target_batch_size}")
        logger.info(f"  Balance score: {balance_score:.3f}")
    
    def validate_no_duplicate_creators(self, batches: List[Dict[str, List[str]]]) -> Dict[str, Any]:
        """
        Validate that no creator appears in multiple batches
        
        Args:
            batches: List of batches to validate
            
        Returns:
            Dictionary with validation results
        """
        try:
            all_creators = set()
            duplicate_creators = set()
            creator_batch_map = {}
            
            for batch_id, batch in enumerate(batches):
                for creator_name in batch.keys():
                    if creator_name in all_creators:
                        duplicate_creators.add(creator_name)
                        logger.error(f"Duplicate creator found: {creator_name} "
                                   f"in batches {creator_batch_map[creator_name]} and {batch_id}")
                    else:
                        all_creators.add(creator_name)
                        creator_batch_map[creator_name] = batch_id
            
            validation_result = {
                'valid': len(duplicate_creators) == 0,
                'total_creators': len(all_creators),
                'duplicate_count': len(duplicate_creators),
                'duplicate_creators': list(duplicate_creators),
                'creator_batch_map': creator_batch_map
            }
            
            if validation_result['valid']:
                logger.info(f"✓ Validation passed: {len(all_creators)} unique creators "
                           f"across {len(batches)} batches")
            else:
                logger.error(f"✗ Validation failed: {len(duplicate_creators)} duplicate creators found")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating batch uniqueness: {e}")
            return {
                'valid': False,
                'error': str(e),
                'total_creators': 0,
                'duplicate_count': 0
            }
    
    def get_creator_batch_assignment(self, creator_name: str) -> Optional[int]:
        """
        Get batch assignment for specific creator
        
        Args:
            creator_name: Name of the creator
            
        Returns:
            Batch ID or None if not assigned
        """
        return self.creator_assignments.get(creator_name)
    
    def get_batch_creators(self, batch_id: int) -> List[str]:
        """
        Get list of creators assigned to specific batch
        
        Args:
            batch_id: ID of the batch
            
        Returns:
            List of creator names in the batch
        """
        return self.batch_creators.get(batch_id, [])
    
    def get_batch_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about batch assignments
        
        Returns:
            Dictionary with batch assignment statistics
        """
        if not self.creator_assignments:
            return {
                'total_creators': 0,
                'total_batches': 0,
                'assignments': {}
            }
        
        # Calculate statistics
        total_creators = len(self.creator_assignments)
        total_batches = len(self.batch_creators)
        
        batch_stats = {}
        for batch_id, creators in self.batch_creators.items():
            batch_stats[batch_id] = {
                'creator_count': len(creators),
                'image_count': self.batch_sizes.get(batch_id, 0),
                'creators': creators
            }
        
        return {
            'total_creators': total_creators,
            'total_batches': total_batches,
            'batch_statistics': batch_stats,
            'hash_algorithm': self.hash_algorithm
        }
    
    def export_assignments(self) -> Dict[str, Any]:
        """
        Export all creator-to-batch assignments
        
        Returns:
            Dictionary with all assignment data
        """
        return {
            'creator_assignments': dict(self.creator_assignments),
            'batch_creators': {k: list(v) for k, v in self.batch_creators.items()},
            'batch_sizes': dict(self.batch_sizes),
            'hash_algorithm': self.hash_algorithm,
            'total_creators': len(self.creator_assignments),
            'total_batches': len(self.batch_creators)
        }
    
    def import_assignments(self, assignment_data: Dict[str, Any]):
        """
        Import creator-to-batch assignments
        
        Args:
            assignment_data: Assignment data to import
        """
        try:
            self.creator_assignments = assignment_data.get('creator_assignments', {})
            self.batch_creators = defaultdict(list, assignment_data.get('batch_creators', {}))
            self.batch_sizes = defaultdict(int, assignment_data.get('batch_sizes', {}))
            
            imported_algorithm = assignment_data.get('hash_algorithm', self.hash_algorithm)
            if imported_algorithm != self.hash_algorithm:
                logger.warning(f"Hash algorithm mismatch: current={self.hash_algorithm}, "
                              f"imported={imported_algorithm}")
            
            logger.info(f"Imported assignments for {len(self.creator_assignments)} creators "
                       f"across {len(self.batch_creators)} batches")
            
        except Exception as e:
            logger.error(f"Error importing assignments: {e}")
            raise
    
    def clear_assignments(self):
        """Clear all creator-to-batch assignments"""
        self.creator_assignments.clear()
        self.batch_creators.clear()
        self.batch_sizes.clear()
        logger.info("Cleared all creator-to-batch assignments")
    
    def verify_assignment_integrity(self) -> Dict[str, Any]:
        """
        Verify integrity of current assignments
        
        Returns:
            Dictionary with integrity check results
        """
        try:
            issues = []
            
            # Check consistency between data structures
            for creator_name, batch_id in self.creator_assignments.items():
                if creator_name not in self.batch_creators.get(batch_id, []):
                    issues.append(f"Creator {creator_name} assigned to batch {batch_id} "
                                f"but not in batch creators list")
            
            for batch_id, creators in self.batch_creators.items():
                for creator_name in creators:
                    if self.creator_assignments.get(creator_name) != batch_id:
                        issues.append(f"Creator {creator_name} in batch {batch_id} creators "
                                    f"but assigned to different batch")
            
            # Check for duplicate creators across batches
            all_creators_in_batches = []
            for creators in self.batch_creators.values():
                all_creators_in_batches.extend(creators)
            
            if len(all_creators_in_batches) != len(set(all_creators_in_batches)):
                duplicates = [creator for creator in set(all_creators_in_batches) 
                            if all_creators_in_batches.count(creator) > 1]
                issues.append(f"Duplicate creators found across batches: {duplicates}")
            
            return {
                'integrity_valid': len(issues) == 0,
                'issues': issues,
                'total_creators': len(self.creator_assignments),
                'total_batches': len(self.batch_creators)
            }
            
        except Exception as e:
            logger.error(f"Error verifying assignment integrity: {e}")
            return {
                'integrity_valid': False,
                'error': str(e),
                'issues': [f"Integrity check failed: {str(e)}"]
            }
