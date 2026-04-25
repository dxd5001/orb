#!/usr/bin/env python3
"""
Orb CLI entry point.

This module provides the command-line interface for the Orb application.
"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Also add to PYTHONPATH for subprocess calls
os.environ['PYTHONPATH'] = str(project_root) + ':' + os.environ.get('PYTHONPATH', '')

from menubar_app import main

if __name__ == '__main__':
    if sys.argv[0].endswith('.exe'):
        sys.argv[0] = sys.argv[0][:-4]
    sys.exit(main())
