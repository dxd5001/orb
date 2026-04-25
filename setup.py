#!/usr/bin/env python3
"""
Setup script for Orb - RAG Chatbot for Obsidian Vaults
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8')

# Read requirements
requirements = []
with open('backend/requirements.txt') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="orb",
    version="0.1.0",
    author="Daijiro Miyazawa",
    author_email="dxd5001@gmail.com",
    description="Orb - A private RAG chatbot for Obsidian vaults with multilingual support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dxd5001/orb",
    packages=find_packages(),
    py_modules=["menubar_app", "orb_cli"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Text Processing :: Linguistic",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "hypothesis>=6.88.0",
        ],
        "menubar": [
            "pystray>=0.19.0",
            "Pillow>=9.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "orb=menubar_app:main",
            "orb-mcp=mcp_server:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.md", "*.txt", "*.json"],
        "frontend": ["*.html", "*.js", "*.css"],
    },
    zip_safe=False,
    keywords="orb, obsidian, rag, chatbot, ai, multilingual, japanese, english",
    project_urls={
        "Bug Reports": "https://github.com/dxd5001/orb/issues",
        "Source": "https://github.com/dxd5001/orb",
        "Documentation": "https://github.com/dxd5001/orb/blob/main/README.md",
    },
)
