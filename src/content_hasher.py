"""
Content hashing module for creator fingerprinting and change detection
Generates deterministic hashes based on creator image URLs and metadata
"""

import hashlib
import json
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)

class ContentHasher:
    """Content hashing for creator data fingerprinting"""
    
    def __init__(self, algorithm: str = 'sha256'):
        """
        Initialize content hasher
        
        Args:
            algorithm: Hash algorithm to use ('sha256', 'md5', 'sha1')
        """
        self.algorithm = algorithm.lower()
        
        # Validate algorithm
        if self.algorithm not in ['sha256', 'md5', 'sha1']:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        
        # Get hash function
        self.hash_func = getattr(hashlib, self.algorithm)
        
        logger.info(f"ContentHasher initialized with {self.algorithm} algorithm")
    
    def generate_creator_hash(self, creator_name: str, image_urls: List[str], 
                            metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate deterministic hash for creator based on their image URLs
        
        Args:
            creator_name: Name of the creator
            image_urls: List of image URLs for this creator
            metadata: Optional metadata to include in hash
            
        Returns:
            Hexadecimal hash string
        """
        try:
            # Prepare data for hashing
            hash_data = {
                'creator_name': creator_name.strip().lower(),
                'image_urls': sorted([url.strip() for url in image_urls if url.strip()]),
                'url_count': len([url for url in image_urls if url.strip()]),
                'metadata': metadata or {}
            }
            
            # Convert to deterministic JSON string
            json_string = json.dumps(hash_data, sort_keys=True, separators=(',', ':'))
            
            # Generate hash
            hash_object = self.hash_func(json_string.encode('utf-8'))
            hash_hex = hash_object.hexdigest()
            
            logger.debug(f"Generated {self.algorithm} hash for creator {creator_name}: {hash_hex[:16]}...")
            
            return hash_hex
            
        except Exception as e:
            logger.error(f"Error generating hash for creator {creator_name}: {e}")
            raise
    
    def generate_batch_hash(self, creators_data: Dict[str, List[str]]) -> str:
        """
        Generate hash for entire batch of creators
        
        Args:
            creators_data: Dictionary mapping creator names to their image URLs
            
        Returns:
            Hexadecimal hash string for the batch
        """
        try:
            # Generate individual creator hashes
            creator_hashes = {}
            for creator_name, image_urls in creators_data.items():
                creator_hashes[creator_name] = self.generate_creator_hash(creator_name, image_urls)
            
            # Create batch hash data
            batch_data = {
                'creator_count': len(creators_data),
                'total_urls': sum(len(urls) for urls in creators_data.values()),
                'creator_hashes': dict(sorted(creator_hashes.items()))
            }
            
            # Convert to deterministic JSON string
            json_string = json.dumps(batch_data, sort_keys=True, separators=(',', ':'))
            
            # Generate hash
            hash_object = self.hash_func(json_string.encode('utf-8'))
            batch_hash = hash_object.hexdigest()
            
            logger.info(f"Generated batch hash for {len(creators_data)} creators: {batch_hash[:16]}...")
            
            return batch_hash
            
        except Exception as e:
            logger.error(f"Error generating batch hash: {e}")
            raise
    
    def generate_url_set_hash(self, urls: List[str]) -> str:
        """
        Generate hash for a set of URLs (order-independent)
        
        Args:
            urls: List of URLs to hash
            
        Returns:
            Hexadecimal hash string
        """
        try:
            # Clean and deduplicate URLs
            clean_urls = list(set(url.strip() for url in urls if url.strip()))
            
            # Sort for deterministic results
            sorted_urls = sorted(clean_urls)
            
            # Create hash data
            hash_data = {
                'urls': sorted_urls,
                'count': len(sorted_urls)
            }
            
            # Convert to JSON and hash
            json_string = json.dumps(hash_data, sort_keys=True, separators=(',', ':'))
            hash_object = self.hash_func(json_string.encode('utf-8'))
            
            return hash_object.hexdigest()
            
        except Exception as e:
            logger.error(f"Error generating URL set hash: {e}")
            raise
    
    def compare_creator_content(self, creator_name: str, 
                              old_urls: List[str], new_urls: List[str]) -> Dict[str, Any]:
        """
        Compare two sets of creator content and detect changes
        
        Args:
            creator_name: Name of the creator
            old_urls: Previous set of image URLs
            new_urls: New set of image URLs
            
        Returns:
            Dictionary with comparison results
        """
        try:
            # Generate hashes
            old_hash = self.generate_creator_hash(creator_name, old_urls)
            new_hash = self.generate_creator_hash(creator_name, new_urls)
            
            # Clean URL sets for comparison
            old_set = set(url.strip() for url in old_urls if url.strip())
            new_set = set(url.strip() for url in new_urls if url.strip())
            
            # Calculate changes
            added_urls = new_set - old_set
            removed_urls = old_set - new_set
            common_urls = old_set & new_set
            
            comparison = {
                'creator_name': creator_name,
                'content_changed': old_hash != new_hash,
                'old_hash': old_hash,
                'new_hash': new_hash,
                'old_count': len(old_set),
                'new_count': len(new_set),
                'added_count': len(added_urls),
                'removed_count': len(removed_urls),
                'common_count': len(common_urls),
                'added_urls': list(added_urls),
                'removed_urls': list(removed_urls),
                'change_summary': self._generate_change_summary(len(added_urls), len(removed_urls), len(common_urls))
            }
            
            logger.info(f"Content comparison for {creator_name}: {comparison['change_summary']}")
            
            return comparison
            
        except Exception as e:
            logger.error(f"Error comparing content for creator {creator_name}: {e}")
            raise
    
    def _generate_change_summary(self, added: int, removed: int, common: int) -> str:
        """
        Generate human-readable change summary
        
        Args:
            added: Number of added URLs
            removed: Number of removed URLs
            common: Number of unchanged URLs
            
        Returns:
            Change summary string
        """
        if added == 0 and removed == 0:
            return "No changes"
        
        parts = []
        if added > 0:
            parts.append(f"+{added}")
        if removed > 0:
            parts.append(f"-{removed}")
        if common > 0:
            parts.append(f"={common}")
            
        return " ".join(parts)
    
    def generate_deterministic_filename(self, creator_name: str, 
                                      content_hash: str, 
                                      file_extension: str = 'jpg') -> str:
        """
        Generate deterministic filename based on creator and content
        
        Args:
            creator_name: Name of the creator
            content_hash: Content hash for the creator
            file_extension: File extension (default: 'jpg')
            
        Returns:
            Deterministic filename
        """
        try:
            # Sanitize creator name for filename
            safe_creator_name = "".join(c for c in creator_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_creator_name = safe_creator_name.replace(' ', '_').lower()
            
            # Use first 12 characters of hash for filename
            hash_prefix = content_hash[:12]
            
            # Generate filename
            filename = f"{safe_creator_name}_collage_{hash_prefix}.{file_extension}"
            
            logger.debug(f"Generated deterministic filename: {filename}")
            
            return filename
            
        except Exception as e:
            logger.error(f"Error generating filename for creator {creator_name}: {e}")
            raise
    
    def validate_hash(self, hash_string: str) -> bool:
        """
        Validate hash string format
        
        Args:
            hash_string: Hash string to validate
            
        Returns:
            True if valid hash format
        """
        if not hash_string:
            return False
        
        # Expected lengths for different algorithms
        expected_lengths = {
            'md5': 32,
            'sha1': 40,
            'sha256': 64
        }
        
        expected_length = expected_lengths.get(self.algorithm)
        if not expected_length:
            return False
        
        # Check length and hex characters
        if len(hash_string) != expected_length:
            return False
        
        try:
            int(hash_string, 16)  # Validate hex format
            return True
        except ValueError:
            return False
    
    def get_hash_info(self) -> Dict[str, Any]:
        """
        Get information about the current hash configuration
        
        Returns:
            Dictionary with hash configuration info
        """
        expected_lengths = {
            'md5': 32,
            'sha1': 40,
            'sha256': 64
        }
        
        return {
            'algorithm': self.algorithm,
            'hash_length': expected_lengths.get(self.algorithm, 0),
            'security_level': 'high' if self.algorithm == 'sha256' else 'medium' if self.algorithm == 'sha1' else 'low'
        }
    
    def create_processing_fingerprint(self, creator_name: str, image_urls: List[str],
                                    processing_config: Dict[str, Any]) -> str:
        """
        Create fingerprint that includes both content and processing configuration
        
        Args:
            creator_name: Name of the creator
            image_urls: List of image URLs
            processing_config: Processing configuration parameters
            
        Returns:
            Combined fingerprint hash
        """
        try:
            # Create comprehensive fingerprint data
            fingerprint_data = {
                'creator_name': creator_name.strip().lower(),
                'image_urls': sorted([url.strip() for url in image_urls if url.strip()]),
                'processing_config': dict(sorted(processing_config.items())),
                'timestamp': datetime.utcnow().strftime('%Y-%m-%d')  # Date only for daily uniqueness
            }
            
            # Convert to JSON and hash
            json_string = json.dumps(fingerprint_data, sort_keys=True, separators=(',', ':'))
            hash_object = self.hash_func(json_string.encode('utf-8'))
            fingerprint = hash_object.hexdigest()
            
            logger.debug(f"Generated processing fingerprint for {creator_name}: {fingerprint[:16]}...")
            
            return fingerprint
            
        except Exception as e:
            logger.error(f"Error generating processing fingerprint for {creator_name}: {e}")
            raise
