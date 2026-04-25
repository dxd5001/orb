#!/bin/bash
# Installation script for Orb - RAG Chatbot for Obsidian Vaults

set -e

echo "🚀 Installing Orb - RAG Chatbot for Obsidian Vaults..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python 3.8 or higher is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version check passed: $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r backend/requirements.txt

# Install the package in development mode
echo "🔧 Installing package in development mode..."
pip install -e .

# Create configuration file
if [ ! -f ".env" ]; then
    echo "⚙️ Creating configuration file..."
    cp .env.example .env
    echo "📝 Please edit .env file with your settings:"
    echo "   - VAULT_PATH: Path to your Obsidian vault"
    echo "   - LLM_PROVIDER: 'local' or 'openai'"
    echo "   - LLM_MODEL: Model name"
    echo "   - For OpenAI: Set LLM_API_KEY"
fi

echo "✅ Installation completed!"
echo ""
echo "🎯 Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Run the menu bar app: orb"
echo "3. Or start web server directly: cd backend && python main.py"
echo ""
echo "📖 For more information, see README.md"
