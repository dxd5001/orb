"""
Obsidian vault ingestor implementation.

This module provides the concrete implementation for ingesting Obsidian vaults.
It reads Markdown files recursively, parses frontmatter, and extracts metadata
according to the specification.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

try:
    import frontmatter
    FRONTMATTER_AVAILABLE = True
except ImportError:
    FRONTMATTER_AVAILABLE = False
    frontmatter = None

from .base import BaseIngestor
from models import NoteDocument, IngestResult
from .base import sanitize_text, extract_metadata_from_path


logger = logging.getLogger(__name__)


class ObsidianIngestor(BaseIngestor):
    """
    Ingestor for Obsidian vaults.
    
    This ingestor reads Markdown files from an Obsidian vault directory,
    parses frontmatter, extracts metadata, and creates NoteDocument objects.
    
    Features:
    - Recursive directory traversal
    - Frontmatter parsing and separation
    - Metadata extraction (title, tags, file info)
    - Error resilience (continues processing on individual file failures)
    - Comprehensive logging and statistics
    """
    
    def __init__(self, use_python_frontmatter: bool = True):
        """
        Initialize ObsidianIngestor.
        
        Args:
            use_python_frontmatter: Whether to use python-frontmatter library
                                  if available, otherwise fall back to regex parsing
        """
        self.use_python_frontmatter = use_python_frontmatter and FRONTMATTER_AVAILABLE
        
        if not self.use_python_frontmatter:
            logger.info("Using regex-based frontmatter parsing")
    
    def ingest(self, source_path: str) -> IngestResult:
        """
        Ingest all Markdown files from the specified vault path.
        
        Args:
            source_path: Path to the Obsidian vault directory
            
        Returns:
            IngestResult with processed notes and statistics
            
        Raises:
            ValueError: If source_path is not a valid directory
            PermissionError: If lacking permissions to access the vault
        """
        self.log_ingestion_start(source_path)
        
        if not self.validate_source_path(source_path):
            raise ValueError(f"Invalid vault path: {source_path}")
        
        notes = []
        errors = []
        
        try:
            # Find all Markdown files recursively
            md_files = self._find_markdown_files(source_path)
            logger.info(f"Found {len(md_files)} Markdown files in vault")
            
            # Process each file
            for file_path in md_files:
                try:
                    note = self._process_markdown_file(file_path, source_path)
                    if note:
                        notes.append(note)
                except Exception as e:
                    error_msg = f"Failed to process file: {str(e)}"
                    errors.append(self.create_error_entry(file_path, error_msg))
                    logger.warning(f"Error processing {file_path}: {e}")
            
        except Exception as e:
            logger.error(f"Vault ingestion failed: {e}")
            raise
        
        result = self.calculate_ingestion_stats(notes, errors)
        self.log_ingestion_complete(result)
        
        return result
    
    def validate_source_path(self, source_path: str) -> bool:
        """
        Validate that the vault path exists and is a directory.
        
        Args:
            source_path: Path to validate
            
        Returns:
            True if path is a valid directory, False otherwise
        """
        try:
            path = Path(source_path)
            return path.exists() and path.is_dir()
        except Exception as e:
            logger.error(f"Error validating vault path '{source_path}': {e}")
            return False
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.
        
        Returns:
            List of supported Markdown file extensions
        """
        return ['.md', '.markdown']
    
    def get_ingestor_name(self) -> str:
        """
        Get the ingestor name for identification.
        
        Returns:
            Ingestor name
        """
        return "ObsidianIngestor"
    
    def _find_markdown_files(self, vault_path: str) -> List[str]:
        """
        Find all Markdown files in the vault recursively.
        
        Args:
            vault_path: Path to the vault directory
            
        Returns:
            List of absolute file paths for all Markdown files
        """
        vault_dir = Path(vault_path)
        md_files = []
        
        for ext in self.get_supported_extensions():
            # Find files with each supported extension
            pattern = f"**/*{ext}"
            files = vault_dir.glob(pattern)
            md_files.extend([str(f) for f in files])
        
        # Sort for consistent processing order
        md_files.sort()
        
        return md_files
    
    def _process_markdown_file(self, file_path: str, vault_path: str) -> Optional[NoteDocument]:
        """
        Process a single Markdown file and create a NoteDocument.
        
        Args:
            file_path: Absolute path to the Markdown file
            vault_path: Path to the vault root directory
            
        Returns:
            NoteDocument or None if processing failed
        """
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter and extract body
            frontmatter_data, body_text = self._parse_frontmatter(content)
            
            # Extract metadata
            relative_path = os.path.relpath(file_path, vault_path)
            title = self._extract_title(frontmatter_data, relative_path)
            tags = self._extract_tags(frontmatter_data)
            last_modified = self._get_last_modified(file_path)
            
            # Sanitize body text
            body_text = sanitize_text(body_text)
            
            # Create NoteDocument
            note = NoteDocument(
                file_path=relative_path,
                title=title,
                body=body_text,
                tags=tags,
                frontmatter=frontmatter_data,
                last_modified=last_modified
            )
            
            return note
            
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")
            raise
    
    def _parse_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
        """
        Parse frontmatter from Markdown content.
        
        Args:
            content: Raw file content
            
        Returns:
            Tuple of (frontmatter_dict, body_text)
        """
        if self.use_python_frontmatter:
            return self._parse_frontmatter_with_library(content)
        else:
            return self._parse_frontmatter_with_regex(content)
    
    def _parse_frontmatter_with_library(self, content: str) -> Tuple[Dict[str, Any], str]:
        """
        Parse frontmatter using python-frontmatter library.
        
        Args:
            content: Raw file content
            
        Returns:
            Tuple of (frontmatter_dict, body_text)
        """
        try:
            post = frontmatter.loads(content)
            frontmatter_data = post.metadata
            body_text = post.content
            
            # Ensure frontmatter_data is a dictionary
            if not isinstance(frontmatter_data, dict):
                frontmatter_data = {}
            
            return frontmatter_data, body_text
            
        except Exception as e:
            logger.warning(f"Failed to parse frontmatter with library: {e}")
            # Fall back to regex parsing
            return self._parse_frontmatter_with_regex(content)
    
    def _parse_frontmatter_with_regex(self, content: str) -> Tuple[Dict[str, Any], str]:
        """
        Parse frontmatter using regular expressions.
        
        Args:
            content: Raw file content
            
        Returns:
            Tuple of (frontmatter_dict, body_text)
        """
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)
        
        if match:
            frontmatter_text, body_text = match.groups()
            
            try:
                # Simple YAML parsing for basic structures
                frontmatter_data = self._parse_simple_yaml(frontmatter_text)
                return frontmatter_data, body_text
            except Exception as e:
                logger.warning(f"Failed to parse frontmatter YAML: {e}")
                # Return empty frontmatter and full content as body
                return {}, content
        else:
            # No frontmatter found
            return {}, content
    
    def _parse_simple_yaml(self, yaml_text: str) -> Dict[str, Any]:
        """
        Parse simple YAML key-value pairs.
        
        This is a basic YAML parser that handles common frontmatter formats.
        It's not a full YAML parser but handles the most common cases.
        
        Args:
            yaml_text: YAML text from frontmatter
            
        Returns:
            Dictionary of parsed key-value pairs
        """
        data = {}
        lines = yaml_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Handle key: value pairs
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # Handle boolean values
                if value.lower() in ['true', 'yes', 'on']:
                    value = True
                elif value.lower() in ['false', 'no', 'off']:
                    value = False
                # Handle numeric values
                elif value.isdigit():
                    value = int(value)
                elif value.replace('.', '', 1).isdigit():
                    value = float(value)
                
                data[key] = value
            
            # Handle list items (starting with -)
            elif line.startswith('-'):
                item = line[1:].strip()
                # Remove quotes if present
                if item.startswith('"') and item.endswith('"'):
                    item = item[1:-1]
                elif item.startswith("'") and item.endswith("'"):
                    item = item[1:-1]
                
                # Add to last key as list (assuming it was tags or similar)
                if 'tags' in data:
                    if not isinstance(data['tags'], list):
                        data['tags'] = [data['tags']]
                    data['tags'].append(item)
                else:
                    data['tags'] = [item]
        
        return data
    
    def _extract_title(self, frontmatter_data: Dict[str, Any], relative_path: str) -> str:
        """
        Extract title from frontmatter or filename.
        
        Args:
            frontmatter_data: Parsed frontmatter dictionary
            relative_path: Relative file path
            
        Returns:
            Extracted title
        """
        # Try frontmatter title first
        if 'title' in frontmatter_data:
            title = frontmatter_data['title']
            if isinstance(title, str) and title.strip():
                return sanitize_text(title.strip())
        
        # Fall back to filename without extension
        filename = os.path.basename(relative_path)
        title = os.path.splitext(filename)[0]
        
        return sanitize_text(title)
    
    def _extract_tags(self, frontmatter_data: Dict[str, Any]) -> List[str]:
        """
        Extract tags from frontmatter.
        
        Args:
            frontmatter_data: Parsed frontmatter dictionary
            
        Returns:
            List of tags
        """
        tags = []
        
        # Handle tags field
        if 'tags' in frontmatter_data:
            tags_value = frontmatter_data['tags']
            
            if isinstance(tags_value, list):
                tags = [str(tag).strip() for tag in tags_value if tag]
            elif isinstance(tags_value, str):
                # Handle comma-separated tags
                if ',' in tags_value:
                    tags = [tag.strip() for tag in tags_value.split(',') if tag.strip()]
                else:
                    tags = [tags_value.strip()] if tags_value.strip() else []
        
        # Filter out empty tags and ensure they're strings
        tags = [tag for tag in tags if tag and isinstance(tag, str)]
        
        return tags
    
    def _get_last_modified(self, file_path: str) -> datetime:
        """
        Get the last modification time for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Last modification datetime
        """
        try:
            stat = os.stat(file_path)
            return datetime.fromtimestamp(stat.st_mtime)
        except Exception as e:
            logger.warning(f"Failed to get modification time for {file_path}: {e}")
            return datetime.now()


# Register the ingestor with the factory
from .base import IngestorFactory
IngestorFactory.register_ingestor("obsidian", ObsidianIngestor)
