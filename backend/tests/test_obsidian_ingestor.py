"""
Tests for ObsidianIngestor.

This module tests the concrete implementation for ingesting Obsidian vaults.
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

from backend.ingestion.obsidian import ObsidianIngestor
from backend.models import NoteDocument, IngestResult


class TestObsidianIngestor:
    """Test cases for ObsidianIngestor."""
    
    def create_test_vault(self, files: dict) -> str:
        """
        Create a temporary vault with test files.
        
        Args:
            files: Dictionary of file paths to content
            
        Returns:
            Path to the temporary vault directory
        """
        vault_dir = tempfile.mkdtemp()
        
        for file_path, content in files.items():
            full_path = os.path.join(vault_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        return vault_dir
    
    def test_init_with_frontmatter_library(self):
        """Test initialization when frontmatter library is available."""
        with patch('backend.ingestion.obsidian.FRONTMATTER_AVAILABLE', True):
            ingestor = ObsidianIngestor(use_python_frontmatter=True)
            assert ingestor.use_python_frontmatter is True
    
    def test_init_without_frontmatter_library(self):
        """Test initialization when frontmatter library is not available."""
        with patch('backend.ingestion.obsidian.FRONTMATTER_AVAILABLE', False):
            ingestor = ObsidianIngestor(use_python_frontmatter=True)
            assert ingestor.use_python_frontmatter is False
    
    def test_get_supported_extensions(self):
        """Test getting supported file extensions."""
        ingestor = ObsidianIngestor()
        extensions = ingestor.get_supported_extensions()
        assert '.md' in extensions
        assert '.markdown' in extensions
        assert len(extensions) == 2
    
    def test_get_ingestor_name(self):
        """Test getting ingestor name."""
        ingestor = ObsidianIngestor()
        assert ingestor.get_ingestor_name() == "ObsidianIngestor"
    
    def test_validate_source_path_valid(self):
        """Test validation with valid directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            ingestor = ObsidianIngestor()
            assert ingestor.validate_source_path(temp_dir) is True
    
    def test_validate_source_path_invalid(self):
        """Test validation with invalid paths."""
        ingestor = ObsidianIngestor()
        
        # Non-existent path
        assert ingestor.validate_source_path('/nonexistent') is False
        
        # File instead of directory
        with tempfile.NamedTemporaryFile() as temp_file:
            assert ingestor.validate_source_path(temp_file.name) is False
    
    def test_ingest_empty_vault(self):
        """Test ingesting an empty vault."""
        with tempfile.TemporaryDirectory() as vault_dir:
            ingestor = ObsidianIngestor()
            result = ingestor.ingest(vault_dir)
            
            assert isinstance(result, IngestResult)
            assert len(result.notes) == 0
            assert result.total_count == 0
            assert result.skipped_count == 0
            assert len(result.errors) == 0
    
    def test_ingest_simple_vault(self):
        """Test ingesting a vault with simple Markdown files."""
        files = {
            'note1.md': '# First Note\n\nThis is the content of note 1.',
            'note2.md': '# Second Note\n\nThis is the content of note 2.',
            'subfolder/note3.md': '# Third Note\n\nThis is in a subfolder.'
        }
        
        vault_dir = self.create_test_vault(files)
        
        try:
            ingestor = ObsidianIngestor()
            result = ingestor.ingest(vault_dir)
            
            assert len(result.notes) == 3
            assert result.total_count == 3
            assert result.skipped_count == 0
            assert len(result.errors) == 0
            
            # Check note content
            note_paths = [note.file_path for note in result.notes]
            assert 'note1.md' in note_paths
            assert 'note2.md' in note_paths
            assert 'subfolder/note3.md' in note_paths
            
            # Check titles (derived from filenames)
            for note in result.notes:
                assert note.title in ['note1', 'note2', 'note3']
                assert note.body.startswith('#')
                assert len(note.tags) == 0
                
        finally:
            # Clean up
            import shutil
            shutil.rmtree(vault_dir)
    
    def test_ingest_with_frontmatter_library(self):
        """Test ingesting files with frontmatter using library."""
        files = {
            'note1.md': '''---
title: Custom Title
tags: [test, important]
author: John Doe
---

# Note Content

This is the content with custom title and tags.
''',
            'note2.md': '''---
title: Another Note
tags: work, project
---

# Another Content

More content here.
'''
        }
        
        vault_dir = self.create_test_vault(files)
        
        try:
            with patch('backend.ingestion.obsidian.FRONTMATTER_AVAILABLE', True):
                ingestor = ObsidianIngestor(use_python_frontmatter=True)
                result = ingestor.ingest(vault_dir)
            
            assert len(result.notes) == 2
            
            # Check first note
            note1 = next(n for n in result.notes if n.file_path == 'note1.md')
            assert note1.title == 'Custom Title'
            assert 'test' in note1.tags
            assert 'important' in note1.tags
            assert note1.frontmatter['title'] == 'Custom Title'
            assert note1.frontmatter['author'] == 'John Doe'
            assert 'Note Content' in note1.body
            
            # Check second note
            note2 = next(n for n in result.notes if n.file_path == 'note2.md')
            assert note2.title == 'Another Note'
            assert 'work' in note2.tags
            assert 'project' in note2.tags
            
        finally:
            import shutil
            shutil.rmtree(vault_dir)
    
    def test_ingest_with_regex_frontmatter(self):
        """Test ingesting files with frontmatter using regex parsing."""
        files = {
            'note1.md': '''---
title: Regex Title
tags: test, simple
---

# Regex Content

Content parsed with regex.
'''
        }
        
        vault_dir = self.create_test_vault(files)
        
        try:
            with patch('backend.ingestion.obsidian.FRONTMATTER_AVAILABLE', False):
                ingestor = ObsidianIngestor(use_python_frontmatter=False)
                result = ingestor.ingest(vault_dir)
            
            assert len(result.notes) == 1
            
            note = result.notes[0]
            assert note.title == 'Regex Title'
            assert 'test' in note.tags
            assert 'simple' in note.tags
            assert 'Regex Content' in note.body
            
        finally:
            import shutil
            shutil.rmtree(vault_dir)
    
    def test_ingest_with_various_frontmatter_formats(self):
        """Test ingesting files with various frontmatter formats."""
        files = {
            'string_tags.md': '''---
title: String Tags
tags: tag1, tag2, tag3
---

Content with string tags.
''',
            'boolean_field.md': '''---
title: Boolean Test
published: true
draft: false
---

Content with boolean fields.
''',
            'numeric_field.md': '''---
title: Numeric Test
priority: 5
rating: 4.5
---

Content with numeric fields.
''',
            'no_frontmatter.md': '''# No Frontmatter

This note has no frontmatter.
'''
        }
        
        vault_dir = self.create_test_vault(files)
        
        try:
            with patch('backend.ingestion.obsidian.FRONTMATTER_AVAILABLE', False):
                ingestor = ObsidianIngestor(use_python_frontmatter=False)
                result = ingestor.ingest(vault_dir)
            
            assert len(result.notes) == 4
            
            # Check string tags
            string_note = next(n for n in result.notes if n.file_path == 'string_tags.md')
            assert string_note.title == 'String Tags'
            assert 'tag1' in string_note.tags
            assert 'tag2' in string_note.tags
            assert 'tag3' in string_note.tags
            
            # Check boolean fields
            bool_note = next(n for n in result.notes if n.file_path == 'boolean_field.md')
            assert bool_note.frontmatter['published'] is True
            assert bool_note.frontmatter['draft'] is False
            
            # Check numeric fields
            num_note = next(n for n in result.notes if n.file_path == 'numeric_field.md')
            assert num_note.frontmatter['priority'] == 5
            assert num_note.frontmatter['rating'] == 4.5
            
            # Check no frontmatter
            no_fm_note = next(n for n in result.notes if n.file_path == 'no_frontmatter.md')
            assert no_fm_note.title == 'no_frontmatter'
            assert len(no_fm_note.frontmatter) == 0
            
        finally:
            import shutil
            shutil.rmtree(vault_dir)
    
    def test_ingest_with_file_errors(self):
        """Test ingesting vault with problematic files."""
        files = {
            'good.md': '# Good Note\n\nThis is fine.',
            'unreadable.md': '# Unreadable\n\nContent here.',
            'empty.md': '',
            'subfolder/nested.md': '# Nested\n\nNested content.'
        }
        
        vault_dir = self.create_test_vault(files)
        
        # Make one file unreadable
        unreadable_path = os.path.join(vault_dir, 'unreadable.md')
        os.chmod(unreadable_path, 0o000)
        
        try:
            ingestor = ObsidianIngestor()
            result = ingestor.ingest(vault_dir)
            
            # Should process 3 files, skip 1
            assert result.total_count == 3
            assert result.skipped_count == 1
            assert len(result.errors) == 1
            
            # Check error details
            error = result.errors[0]
            assert 'unreadable.md' in error['path']
            assert 'Failed to process file' in error['reason']
            
            # Check processed files
            note_paths = [note.file_path for note in result.notes]
            assert 'good.md' in note_paths
            assert 'empty.md' in note_paths
            assert 'subfolder/nested.md' in note_paths
            
        finally:
            # Restore permissions for cleanup
            os.chmod(unreadable_path, 0o644)
            import shutil
            shutil.rmtree(vault_dir)
    
    def test_ingest_invalid_vault_path(self):
        """Test ingesting with invalid vault path."""
        ingestor = ObsidianIngestor()
        
        with pytest.raises(ValueError, match="Invalid vault path"):
            ingestor.ingest('/nonexistent/path')
    
    def test_find_markdown_files(self):
        """Test finding Markdown files in vault."""
        files = {
            'note1.md': 'Content 1',
            'note2.markdown': 'Content 2',
            'subfolder/note3.md': 'Content 3',
            'other.txt': 'Not markdown',
            'subfolder/note4.md': 'Content 4'
        }
        
        vault_dir = self.create_test_vault(files)
        
        try:
            ingestor = ObsidianIngestor()
            md_files = ingestor._find_markdown_files(vault_dir)
            
            assert len(md_files) == 4
            
            # Check that all expected files are found
            file_names = [os.path.basename(f) for f in md_files]
            assert 'note1.md' in file_names
            assert 'note2.markdown' in file_names
            assert 'note3.md' in file_names
            assert 'note4.md' in file_names
            assert 'other.txt' not in file_names
            
        finally:
            import shutil
            shutil.rmtree(vault_dir)
    
    def test_process_markdown_file(self):
        """Test processing a single Markdown file."""
        content = '''---
title: Test Note
tags: test, example
---

# Test Content

This is the body content.
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_file = f.name
        
        try:
            ingestor = ObsidianIngestor()
            note = ingestor._process_markdown_file(temp_file, os.path.dirname(temp_file))
            
            assert isinstance(note, NoteDocument)
            assert note.title == 'Test Note'
            assert 'test' in note.tags
            assert 'example' in note.tags
            assert 'Test Content' in note.body
            assert note.frontmatter['title'] == 'Test Note'
            assert isinstance(note.last_modified, datetime)
            
        finally:
            os.unlink(temp_file)
    
    def test_extract_title_from_filename(self):
        """Test title extraction from filename when no frontmatter title."""
        content = '# Simple Note\n\nNo frontmatter title here.'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_file = f.name
        
        try:
            ingestor = ObsidianIngestor()
            note = ingestor._process_markdown_file(temp_file, os.path.dirname(temp_file))
            
            # Title should be derived from filename
            expected_title = os.path.splitext(os.path.basename(temp_file))[0]
            assert note.title == expected_title
            
        finally:
            os.unlink(temp_file)
    
    def test_extract_tags_various_formats(self):
        """Test tag extraction from various formats."""
        test_cases = [
            (['tag1', 'tag2'], ['tag1', 'tag2']),  # List format
            ('tag1, tag2, tag3', ['tag1', 'tag2', 'tag3']),  # Comma-separated
            ('single_tag', ['single_tag']),  # Single string
            ('', []),  # Empty string
            ([], []),  # Empty list
        ]
        
        for tags_input, expected in test_cases:
            frontmatter = {'tags': tags_input}
            ingestor = ObsidianIngestor()
            result = ingestor._extract_tags(frontmatter)
            assert result == expected, f"Failed for input: {tags_input}"
    
    def test_parse_simple_yaml(self):
        """Test simple YAML parsing."""
        yaml_text = """
title: Test Title
tags: tag1, tag2
published: true
priority: 5
rating: 4.5
author: "John Doe"
"""
        
        ingestor = ObsidianIngestor()
        result = ingestor._parse_simple_yaml(yaml_text)
        
        assert result['title'] == 'Test Title'
        assert 'tag1' in result['tags']
        assert 'tag2' in result['tags']
        assert result['published'] is True
        assert result['priority'] == 5
        assert result['rating'] == 4.5
        assert result['author'] == 'John Doe'
    
    def test_parse_simple_yaml_with_lists(self):
        """Test YAML parsing with list items."""
        yaml_text = """
tags:
- tag1
- tag2
- tag3
"""
        
        ingestor = ObsidianIngestor()
        result = ingestor._parse_simple_yaml(yaml_text)
        
        assert 'tags' in result
        assert isinstance(result['tags'], list)
        assert 'tag1' in result['tags']
        assert 'tag2' in result['tags']
        assert 'tag3' in result['tags']


if __name__ == '__main__':
    pytest.main([__file__])
