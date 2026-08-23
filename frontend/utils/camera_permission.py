"""
Camera Permission Handler for SmartARTrainer
Handles requesting, managing, and storing camera permissions
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt6.QtCore import Qt


class CameraPermissionDialog:
    """Handles camera permission requests"""
    
    def __init__(self, parent=None):
        self.parent = parent
        self.permission_granted = False
        self.permission_denied_once = False
    
    def request_permission(self) -> bool:
        """
        Show camera permission dialog.
        Returns True if permission granted, False if denied.
        """
        if self.permission_granted:
            return True
        
        dialog = QDialog(self.parent)
        dialog.setWindowTitle("Camera Permission Required")
        dialog.setFixedSize(480, 220)
        dialog.setModal(True)
        
        dialog.setStyleSheet("""
            QDialog { 
                background-color: #0f0f10; 
                border: 1px solid #2a2a2a; 
                border-radius: 10px; 
            }
            QLabel { 
                color: white; 
                font-size: 14px; 
                background: transparent;
            }
            QPushButton {
                background: transparent; 
                color: white; 
                font-size: 14px; 
                font-weight: 600;
                min-width: 80px; 
                min-height: 40px; 
                border: 1px solid rgba(255,255,255,0.75);
                border-radius: 8px;
            }
            QPushButton:hover { 
                background: rgba(255,255,255,0.12); 
            }
            QPushButton:pressed { 
                background: rgba(255,255,255,0.20); 
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Camera Permission Required")
        title.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 600; background: transparent;")
        layout.addWidget(title)
        
        # Message
        message = QLabel(
            "This workout application requires access to your camera to:\n"
            "• Monitor your workout form and posture\n"
            "• Provide real-time feedback on your exercises\n"
            "• Track your workout progress\n\n"
            "Do you want to allow camera access?"
        )
        message.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        message.setWordWrap(True)
        message.setStyleSheet("color: #b3b3b3; font-size: 13px; background: transparent;")
        layout.addWidget(message)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        allow_btn = QPushButton("Allow Camera Access")
        allow_btn.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.2); 
                color: #10b981; 
                font-size: 14px; 
                font-weight: 600;
                min-width: 120px; 
                min-height: 40px; 
                border: 1px solid #10b981;
                border-radius: 8px;
            }
            QPushButton:hover { 
                background: rgba(16, 185, 129, 0.3); 
            }
            QPushButton:pressed { 
                background: rgba(16, 185, 129, 0.4); 
            }
        """)
        
        deny_btn = QPushButton("Deny Access")
        deny_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2); 
                color: #ef4444; 
                font-size: 14px; 
                font-weight: 600;
                min-width: 120px; 
                min-height: 40px; 
                border: 1px solid #ef4444;
                border-radius: 8px;
            }
            QPushButton:hover { 
                background: rgba(239, 68, 68, 0.3); 
            }
            QPushButton:pressed { 
                background: rgba(239, 68, 68, 0.4); 
            }
        """)
        
        btn_layout.addStretch()
        btn_layout.addWidget(allow_btn)
        btn_layout.addWidget(deny_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        # Connect buttons
        allow_btn.clicked.connect(dialog.accept)
        deny_btn.clicked.connect(dialog.reject)
        
        # Show dialog and get result
        result = dialog.exec() == QDialog.DialogCode.Accepted
        
        if result:
            self.permission_granted = True
        else:
            self.permission_denied_once = True
            self.show_permission_error()
        
        return result
    
    def show_permission_error(self):
        """Show error message when camera permission is denied"""
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("Camera Permission Denied")
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("Camera Permission Required")
        msg_box.setInformativeText(
            "Camera permission is required to run this workout session.\n\n"
            "The app needs camera access to:\n"
            "• Monitor your exercise form\n"
            "• Provide real-time feedback\n"
            "• Track your workout progress\n\n"
            "Please enable camera permissions and try again."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #0f0f10;
            }
            QMessageBox QLabel {
                color: white;
                background: transparent;
            }
            QPushButton {
                background: rgba(102, 126, 234, 0.3);
                color: white;
                border: 1px solid rgba(102, 126, 234, 0.6);
                border-radius: 6px;
                padding: 6px 20px;
                min-width: 80px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.5);
            }
        """)
        msg_box.exec()
    
    def reset(self):
        """Reset permission state for testing or logout"""
        self.permission_granted = False
        self.permission_denied_once = False
    
    def is_permission_granted(self) -> bool:
        """Check if permission has already been granted"""
        return self.permission_granted
