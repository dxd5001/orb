#!/usr/bin/env python3
"""
Orb - Obsidian RAG Chatbot Menu Bar Application

A system tray application that provides easy access to Orb - the Obsidian RAG Chatbot.
Supports both Web UI and MCP server functionality.
"""

import os
import sys
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import pystray
from PIL import Image, ImageDraw
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrbMenuBarApp:
    """Main Orb menu bar application class."""
    
    def __init__(self):
        """Initialize the menu bar application."""
        self.web_server_process: Optional[subprocess.Popen] = None
        self.mcp_server_process: Optional[subprocess.Popen] = None
        self.app_dir = Path(__file__).parent
        self.backend_dir = self.app_dir / "backend"
        
        # Status tracking
        self.web_server_running = False
        self.mcp_server_running = False
        
        # Create menu bar icon
        self.icon = self.create_icon()
        
    def create_icon(self) -> Image.Image:
        """Create a simple icon for the menu bar."""
        # Create a simple 64x64 icon with "Orb" text
        image = Image.new('RGB', (64, 64), color='blue')
        draw = ImageDraw.Draw(image)
        
        # Draw "Orb" text
        try:
            # Try to use a larger font
            draw.text((8, 20), "Orb", fill='white')
        except:
            # Fallback to default font
            draw.text((8, 20), "Orb", fill='white')
            
        return image
    
    def start_web_server(self, icon=None, item=None):
        """Start the web UI server."""
        if self.web_server_running:
            logger.info("Web server is already running")
            return
            
        try:
            logger.info("Starting web server...")
            
            # Check if backend directory exists
            if not self.backend_dir.exists():
                logger.error(f"Backend directory not found: {self.backend_dir}")
                return
            
            # Start the web server
            cmd = [sys.executable, "main.py"]
            self.web_server_process = subprocess.Popen(
                cmd,
                cwd=self.backend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.web_server_running = True
            logger.info("Web server started successfully")
            
            # Open browser after a short delay
            threading.Timer(2.0, self.open_web_ui).start()
            
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
    
    def stop_web_server(self, icon=None, item=None):
        """Stop the web UI server."""
        if not self.web_server_running:
            return
            
        try:
            if self.web_server_process:
                self.web_server_process.terminate()
                self.web_server_process.wait(timeout=5)
                self.web_server_process = None
            
            self.web_server_running = False
            logger.info("Web server stopped")
            
        except Exception as e:
            logger.error(f"Failed to stop web server: {e}")
    
    def start_mcp_server(self, icon=None, item=None):
        """Start the MCP server."""
        if self.mcp_server_running:
            logger.info("MCP server is already running")
            return
            
        try:
            logger.info("Starting MCP server...")
            
            # Check if MCP server script exists
            mcp_script = self.backend_dir / "mcp_server.py"
            if not mcp_script.exists():
                logger.warning(f"MCP server script not found: {mcp_script}")
                return
            
            # Start the MCP server
            cmd = [sys.executable, "mcp_server.py"]
            self.mcp_server_process = subprocess.Popen(
                cmd,
                cwd=self.backend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.mcp_server_running = True
            logger.info("MCP server started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
    
    def stop_mcp_server(self, icon=None, item=None):
        """Stop the MCP server."""
        if not self.mcp_server_running:
            return
            
        try:
            if self.mcp_server_process:
                self.mcp_server_process.terminate()
                self.mcp_server_process.wait(timeout=5)
                self.mcp_server_process = None
            
            self.mcp_server_running = False
            logger.info("MCP server stopped")
            
        except Exception as e:
            logger.error(f"Failed to stop MCP server: {e}")
    
    def open_web_ui(self):
        """Open the web UI in the default browser."""
        try:
            webbrowser.open("http://localhost:8000")
            logger.info("Opened web UI in browser")
        except Exception as e:
            logger.error(f"Failed to open web UI: {e}")
    
    def show_status(self, icon=None, item=None):
        """Show current status."""
        web_status = "Running" if self.web_server_running else "Stopped"
        mcp_status = "Running" if self.mcp_server_running else "Stopped"
        
        status_msg = f"Web Server: {web_status}\nMCP Server: {mcp_status}"
        logger.info(f"Status: {status_msg}")
        
        # In a real implementation, you might show a notification
        # For now, just log it
        print(f"Status: {status_msg}")
    
    def quit_app(self, icon=None, item=None):
        """Quit the application."""
        logger.info("Quitting application...")
        
        # Stop all servers
        self.stop_web_server()
        self.stop_mcp_server()
        
        # Stop the menu bar app
        icon.stop()
    
    def get_menu_items(self):
        """Get the menu items for the tray icon."""
        menu_items = [
            pystray.MenuItem(
                "Web Server",
                pystray.Menu(
                    pystray.MenuItem(
                        "Start Web Server",
                        self.start_web_server,
                        enabled=not self.web_server_running
                    ),
                    pystray.MenuItem(
                        "Stop Web Server", 
                        self.stop_web_server,
                        enabled=self.web_server_running
                    ),
                    pystray.MenuItem(
                        "Open Web UI",
                        self.open_web_ui,
                        enabled=self.web_server_running
                    )
                )
            ),
            pystray.MenuItem(
                "MCP Server",
                pystray.Menu(
                    pystray.MenuItem(
                        "Start MCP Server",
                        self.start_mcp_server,
                        enabled=not self.mcp_server_running
                    ),
                    pystray.MenuItem(
                        "Stop MCP Server",
                        self.stop_mcp_server,
                        enabled=self.mcp_server_running
                    )
                )
            ),
            pystray.MenuItem(
                "Status",
                self.show_status
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Quit",
                self.quit_app
            )
        ]
        
        return pystray.Menu(*menu_items)
    
    def run(self):
        """Run the menu bar application."""
        logger.info("Starting Orb - Obsidian RAG Chatbot menu bar app...")
        
        # Create and run the tray icon
        icon = pystray.Icon(
            "orb",
            self.icon,
            "Orb - Obsidian RAG Chatbot",
            self.get_menu_items()
        )
        
        try:
            icon.run()
        except KeyboardInterrupt:
            logger.info("Application interrupted")
        finally:
            # Cleanup
            self.stop_web_server()
            self.stop_mcp_server()
            logger.info("Application shutdown complete")


def main():
    """Main entry point."""
    try:
        app = OrbMenuBarApp()
        app.run()
    except Exception as e:
        logger.error(f"Application failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
