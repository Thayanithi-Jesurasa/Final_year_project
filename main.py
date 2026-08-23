"""
SmartARTrainer - AI-Powered Fitness Training Applications
Main entry point
"""

import sys
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from frontend.ui.main_window import MainWindow

# ✅ Import TCP server starter
from backend.utils.unity_session_server import start_tcp_server

def main():
    """Main application entry point"""

    # ✅ Start Unity TCP server in background (so PyQt UI won't freeze)
    try:
        server_thread = threading.Thread(target=start_tcp_server, daemon=True)
        server_thread.start()
        print(" Unity TCP server started on background thread")
    except Exception as e:
        print(f" Failed to start Unity TCP server: {e}")

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("SmartARTrainer")
    app.setOrganizationName("SmartARTrainer")

    try:
        from PyQt6.QtGui import QIcon
        app.setWindowIcon(QIcon("frontend/assets/logo.png"))
    except Exception as e:
        print(f"Icon load error: {e}")

    # Apply global stylesheet
    from frontend.utils.styles import get_main_stylesheet
    app.setStyleSheet(get_main_stylesheet())

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()