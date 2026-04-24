"""
Base abstract class for data ingestion.

This module defines the abstract interface that all ingestors must implement.
The design allows for future extension to support multiple data sources
beyond Obsidian vaults (e.g., Notion, local PDFs, etc.).
"""

from abc import ABC, abstractmethod
from typing import List
import logging

from models import NoteDocument, IngestResult


logger = logging.getLogger(__name__)


class BaseIngestor(ABC):
    """
    Abstract base class for data ingestion.
    
    This class defines the interface that all ingestor implementations must follow.
    It provides a common contract for reading data from various sources and
    converting them into standardized NoteDocument objects.
    
    Design Principles:
    - Source Agnostic: Can be implemented for any data source
    - Error Resilient: Continues processing individual item failures
    - Extensible: Easy to add new data source types
    - Testable: Clear interface for mocking and testing
    """
    
    @abstractmethod
    def ingest(self, source_path: str) -> IngestResult:
        """
        Ingest data from the specified source path.
        
        This method must be implemented by concrete ingestor classes.
        It should read all supported documents from the source and convert
        them into NoteDocument objects.
        
        Args:
            source_path: Path or identifier for the data source
            
        Returns:
            IngestResult containing processed notes, statistics, and any errors
            
        Raises:
            ValueError: If source_path is invalid or inaccessible
            PermissionError: If lacking permissions to access the source
            NotImplementedError: If the ingestor doesn't support the source type
        """
        pass
    
    def validate_source_path(self, source_path: str) -> bool:
        """
        Validate that the source path is accessible and supported.
        
        This is a default implementation that can be overridden by subclasses
        to provide source-specific validation logic.
        
        Args:
            source_path: Path or identifier for the data source
            
        Returns:
            True if the source is valid and accessible, False otherwise
        """
        # Default implementation - subclasses should override
        return source_path is not None and len(source_path.strip()) > 0
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of file extensions supported by this ingestor.
        
        Returns:
            List of supported file extensions (e.g., ['.md', '.markdown'])
        """
        # Default implementation - subclasses should override
        return []
    
    def get_ingestor_name(self) -> str:
        """
        Get the name of this ingestor for logging and identification.
        
        Returns:
            Human-readable name of the ingestor
        """
        return self.__class__.__name__
    
    def log_ingestion_start(self, source_path: str) -> None:
        """
        Log the start of ingestion process.
        
        Args:
            source_path: Source being ingested
        """
        logger.info(f"Starting ingestion with {self.get_ingestor_name()}: {source_path}")
    
    def log_ingestion_complete(self, result: IngestResult) -> None:
        """
        Log the completion of ingestion process.
        
        Args:
            result: Result of the ingestion process
        """
        logger.info(
            f"Ingestion completed with {self.get_ingestor_name()}: "
            f"{result.total_count} notes processed, "
            f"{result.skipped_count} skipped, "
            f"{len(result.errors)} errors"
        )
        
        if result.errors:
            logger.warning(f"Ingestion errors: {result.errors}")
    
    def create_error_entry(self, path: str, reason: str) -> dict:
        """
        Create a standardized error entry for the errors list.
        
        Args:
            path: Path or identifier of the item that failed
            reason: Description of the failure
            
        Returns:
            Dictionary with error information
        """
        return {
            "path": path,
            "reason": reason
        }
    
    def calculate_ingestion_stats(self, notes: List[NoteDocument], 
                                errors: List[dict]) -> IngestResult:
        """
        Calculate ingestion statistics and create result object.
        
        Args:
            notes: Successfully processed notes
            errors: List of processing errors
            
        Returns:
            IngestResult with calculated statistics
        """
        total_processed = len(notes)
        skipped_count = len(errors)
        
        return IngestResult(
            notes=notes,
            total_count=total_processed,
            skipped_count=skipped_count,
            errors=errors
        )


class IngestorFactory:
    """
    Factory class for creating appropriate ingestor instances.
    
    This class provides a centralized way to create ingestor instances
    based on source type or configuration. It makes it easy to extend
    the system with new ingestor types.
    """
    
    _ingestors = {}
    
    @classmethod
    def register_ingestor(cls, source_type: str, ingestor_class: type) -> None:
        """
        Register an ingestor class for a specific source type.
        
        Args:
            source_type: String identifier for the source type
            ingestor_class: Class that inherits from BaseIngestor
        """
        if not issubclass(ingestor_class, BaseIngestor):
            raise ValueError(f"Ingestor class must inherit from BaseIngestor")
        
        cls._ingestors[source_type] = ingestor_class
    
    @classmethod
    def create_ingestor(cls, source_type: str, **kwargs) -> BaseIngestor:
        """
        Create an ingestor instance for the specified source type.
        
        Args:
            source_type: Type of data source
            **kwargs: Additional arguments to pass to the ingestor constructor
            
        Returns:
            Instance of the appropriate ingestor
            
        Raises:
            ValueError: If source type is not supported
        """
        if source_type not in cls._ingestors:
            raise ValueError(f"Unsupported source type: {source_type}")
        
        ingestor_class = cls._ingestors[source_type]
        return ingestor_class(**kwargs)
    
    @classmethod
    def get_supported_types(cls) -> List[str]:
        """
        Get list of supported source types.
        
        Returns:
            List of registered source type identifiers
        """
        return list(cls._ingestors.keys())


# Utility functions for ingestor implementations
def sanitize_text(text: str) -> str:
    """
    Sanitize text content by removing problematic characters.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Remove null bytes and other problematic characters
    text = text.replace('\x00', '')
    
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Strip leading/trailing whitespace while preserving internal structure
    text = text.strip()
    
    return text


def extract_metadata_from_path(file_path: str) -> dict:
    """
    Extract basic metadata from file path.
    
    Args:
        file_path: File path to analyze
        
    Returns:
        Dictionary with extracted metadata
    """
    import os
    from datetime import datetime
    
    try:
        stat = os.stat(file_path)
        return {
            'file_size': stat.st_size,
            'last_modified': datetime.fromtimestamp(stat.st_mtime),
            'created': datetime.fromtimestamp(stat.st_ctime)
        }
    except (OSError, IOError):
        return {
            'file_size': 0,
            'last_modified': datetime.now(),
            'created': datetime.now()
        }
