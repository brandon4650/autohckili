# Updated main.py with hardware ban check functionality
import os
import sys
import logging
import traceback
import datetime
import json
import hashlib
import platform
import uuid
import mysql.connector
from mysql.connector import Error
import webbrowser
import tempfile
import socket

# Set up debug file logging with timestamp in filename
log_dir = "debug_logs"
os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(log_dir, f"autohekili_debug_{timestamp}.log")

# Configure logging to both file and console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

from PyQt5.QtWidgets import (QApplication, QMessageBox, QDialog, QVBoxLayout, QLabel, 
                            QLineEdit, QHBoxLayout, QPushButton)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont

# Log uncaught exceptions
def handle_exception(exc_type, exc_value, exc_traceback):
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    print("An error occurred. See log file for details.")

sys.excepthook = handle_exception

# Database connection settings - match the ones from license_manager.py
DB_CONFIG = {
    'host': '127.0.0.1',
    'database': 'auto_hekili_licenses',
    'user': 'root',
    'password': 'ascent',
    'port': 3306
}

# Constants
CONFIG_PATH = "config\\config.json"
LICENSE_FILE = "config/license.json"
DEBUG_DIR = "debug_captures"

# Fallback pre-generated keys from license_manager.py for offline mode
VALID_LICENSE_KEYS = [
    'ZjZKqrBvcfj2K-7i5FtfYg',
    'b05EP2seekgZOzGfXda83A',
    '6D9GV2UYhiV_g9CHr7vRHA',
    'YkZJ0hUavKVrBR14DVKgxQ',
    'DiPdbOP2cm3m8M5B3325LQ',
    'D9HJxb-p19kn7mBSFl4SpA',
    'ajXkWNWX0GHmnffvX5oMRg',
    'W6nNfwj4IfK8FqHfhvlv8A',
    'hAqi54L5geoFR5_Z88g1NQ'
]

class HardwareBanDialog(QDialog):
    """Dialog shown when hardware is banned."""
    
    def __init__(self, ban_reason, hardware_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hardware Banned")
        self.setWindowIcon(QIcon("icons/app_icon.png"))
        self.setFixedSize(480, 380)
        
        # Set window style to match screenshot with blue title bar
        self.setWindowFlags(self.windowFlags() | Qt.MSWindowsFixedSizeDialogHint)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #FFFFFF;
            }
            QLabel {
                color: #FFFFFF;
            }
            QLabel#banTitle {
                font-size: 24px;
                font-weight: bold;
                color: #FF5555;
            }
            QLabel#warningIcon {
                font-size: 36px;
            }
            QLabel#reasonLabel {
                font-size: 14px;
            }
            QLabel#hwIdLabel {
                font-family: monospace;
                padding: 8px;
                background-color: #1A1A1A;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #8A2BE2;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
                min-width: 160px;
            }
            QPushButton:hover {
                background-color: #9D50EC;
            }
        """)
        
        self.setup_ui(ban_reason, hardware_id)
    
    def setup_ui(self, ban_reason, hardware_id):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Warning icon and title in one row
        title_layout = QHBoxLayout()
        
        warning_label = QLabel("⚠")
        warning_label.setObjectName("warningIcon")
        warning_label.setStyleSheet("color: yellow; font-size: 36px;")
        title_layout.addWidget(warning_label)
        
        ban_title = QLabel("Hardware Banned")
        ban_title.setObjectName("banTitle")
        title_layout.addWidget(ban_title)
        title_layout.addStretch()
        
        layout.addLayout(title_layout)
        
        # Ban reason with proper spacing
        if not ban_reason or ban_reason.strip() == "":
            ban_reason = "Banned by administrator"
            
        reason_label = QLabel(f"Your hardware has been banned for the following reason:")
        reason_label.setWordWrap(True)
        reason_label.setObjectName("reasonLabel")
        layout.addWidget(reason_label)
        
        # Add the actual reason in another label
        ban_reason_label = QLabel(ban_reason)
        ban_reason_label.setWordWrap(True)
        ban_reason_label.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        layout.addWidget(ban_reason_label)
        
        # Additional info
        info_label = QLabel("If you believe this is an error, please contact support with your hardware ID:")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Hardware ID display (selectable)
        hw_label = QLabel(hardware_id)
        hw_label.setObjectName("hwIdLabel")
        hw_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hw_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(hw_label)
        
        layout.addStretch()
        
        # Close button centered
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Close Application")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

class DatabaseManager:
    """Manages database connections and license validation using the schema from license_manager.py"""
    
    def __init__(self):
        self.connection = None
        self.offline_mode = False
    
    def connect(self):
        """Try to connect to the MySQL database"""
        try:
            self.connection = mysql.connector.connect(**DB_CONFIG)
            if self.connection.is_connected():
                logging.info("Connected to MySQL database")
                return True
        except Error as e:
            logging.error(f"Error connecting to MySQL database: {e}")
            self.offline_mode = True
            return False
    
    def disconnect(self):
        """Close the database connection"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logging.info("MySQL connection closed")
    
    def validate_license(self, license_key):
        """Check if license key is valid in the database"""
        if self.offline_mode:
            # Fallback to offline validation with hardcoded keys
            return license_key in VALID_LICENSE_KEYS
        
        if not self.connection or not self.connection.is_connected():
            if not self.connect():
                # If connection fails, fall back to offline mode
                return license_key in VALID_LICENSE_KEYS
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Check if license exists in the licenses table and is active
            query = """
                SELECT * FROM licenses 
                WHERE license_key = %s AND status = 'active'
            """
            cursor.execute(query, (license_key,))
            license_record = cursor.fetchone()
            
            cursor.close()
            
            if not license_record:
                logging.info(f"License key {license_key} not found or not active")
                return False
                
            # License exists in database and is active
            return True
            
        except Error as e:
            logging.error(f"Error validating license: {e}")
            # Fall back to offline mode
            self.offline_mode = True
            return license_key in VALID_LICENSE_KEYS
    
    def check_hardware_ban(self, hardware_id):
        """Check if hardware ID is banned and return (is_banned, ban_reason)."""
        if self.offline_mode:
            return False, None
            
        if not self.connection or not self.connection.is_connected():
            if not self.connect():
                return False, None
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Check hardware ban status
            query = """
                SELECT status, ban_reason FROM hardware_ids 
                WHERE hardware_id = %s
            """
            cursor.execute(query, (hardware_id,))
            result = cursor.fetchone()
            
            cursor.close()
            
            if result and result['status'] == 'banned':
                logging.warning(f"Hardware ID {hardware_id} is banned. Reason: {result['ban_reason']}")
                return True, result['ban_reason'] or "No reason provided"
                
            return False, None
                
        except Error as e:
            logging.error(f"Error checking hardware ban: {e}")
            return False, None  # Continue in case of error
    
    def register_hardware_id(self, hardware_id):
        """Register the hardware ID in the hardware_ids table if not exists"""
        if self.offline_mode:
            return True
            
        if not self.connection or not self.connection.is_connected():
            if not self.connect():
                return True
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Check if hardware ID exists
            query = "SELECT * FROM hardware_ids WHERE hardware_id = %s"
            cursor.execute(query, (hardware_id,))
            result = cursor.fetchone()
            
            if not result:
                # Insert new hardware ID
                insert_query = """
                    INSERT INTO hardware_ids (hardware_id) 
                    VALUES (%s)
                """
                cursor.execute(insert_query, (hardware_id,))
                self.connection.commit()
                logging.info(f"Registered new hardware ID: {hardware_id}")
            elif result['status'] == 'banned':
                # Hardware is banned
                logging.warning(f"Hardware ID {hardware_id} is banned")
                cursor.close()
                return False
                
            cursor.close()
            return True
                
        except Error as e:
            logging.error(f"Error registering hardware ID: {e}")
            return True  # Continue in case of error
    
    def check_activation_limit(self, license_key):
        """Check if license has reached activation limit"""
        if self.offline_mode:
            return True
            
        if not self.connection or not self.connection.is_connected():
            if not self.connect():
                return True
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Count activations for this license
            query = """
                SELECT COUNT(*) as count FROM activations 
                WHERE license_key = %s
            """
            cursor.execute(query, (license_key,))
            result = cursor.fetchone()
            
            cursor.close()
            
            # Assuming limit of 2 activations per license
            if result and result['count'] >= 2:
                logging.warning(f"License {license_key} has reached activation limit")
                return False
                
            return True
                
        except Error as e:
            logging.error(f"Error checking activation limit: {e}")
            return True  # Continue in case of error
    
    def activate_license(self, license_key, hardware_id, client_info=None):
        """Activate license for this hardware ID"""
        if self.offline_mode:
            return True
            
        if not self.connection or not self.connection.is_connected():
            if not self.connect():
                return True
        
        success = False
        ip_address = self.get_local_ip()
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # First register hardware ID if needed
            if not self.register_hardware_id(hardware_id):
                # Hardware ID is banned
                self.record_login_attempt(cursor, license_key, hardware_id, False, ip_address, client_info)
                return False
            
            # Check activation limit
            if not self.check_activation_limit(license_key):
                # Too many activations
                self.record_login_attempt(cursor, license_key, hardware_id, False, ip_address, client_info)
                return False
            
            # Check if already activated for this hardware
            query = """
                SELECT * FROM activations 
                WHERE license_key = %s AND hardware_id = %s
            """
            cursor.execute(query, (license_key, hardware_id))
            existing = cursor.fetchone()
            
            if existing:
                # Update last verification
                update_query = """
                    UPDATE activations 
                    SET last_verification = %s 
                    WHERE license_key = %s AND hardware_id = %s
                """
                cursor.execute(update_query, (datetime.datetime.now(), license_key, hardware_id))
            else:
                # New activation
                insert_query = """
                    INSERT INTO activations 
                    (license_key, hardware_id) 
                    VALUES (%s, %s)
                """
                cursor.execute(insert_query, (license_key, hardware_id))
            
            self.connection.commit()
            success = True
            logging.info(f"License {license_key} activated for hardware {hardware_id}")
            
            # Record successful login attempt
            self.record_login_attempt(cursor, license_key, hardware_id, True, ip_address, client_info)
            
            cursor.close()
            return True
                
        except Error as e:
            logging.error(f"Error activating license: {e}")
            
            # Try to record failed login
            try:
                if cursor:
                    self.record_login_attempt(cursor, license_key, hardware_id, False, ip_address, client_info)
            except:
                pass
                
            return False
    
    def record_login_attempt(self, cursor, license_key, hardware_id, success, ip_address, client_info):
        """Record login attempt in login_attempts table"""
        try:
            query = """
                INSERT INTO login_attempts 
                (license_key, hardware_id, success, ip_address, client_info) 
                VALUES (%s, %s, %s, %s, %s)
            """
            client_info_str = str(client_info) if client_info else None
            cursor.execute(query, (license_key, hardware_id, success, ip_address, client_info_str))
            self.connection.commit()
            logging.info(f"Recorded {'successful' if success else 'failed'} login attempt")
        except Error as e:
            logging.error(f"Error recording login attempt: {e}")
    
    def get_local_ip(self):
        """Get local IP address for logging"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

class LicenseWindow(QDialog):
    """License activation window that matches the provided image."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AUTO_Hekili License Activation")
        self.setWindowIcon(QIcon("icons/app_icon.png"))  # Add your icon if available
        self.setFixedSize(600, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #FFFFFF;
            }
            QLabel {
                color: #FFFFFF;
            }
            QLineEdit {
                background-color: transparent;
                border: none;
                border-bottom: 1px solid #555555;
                color: white;
                padding: 5px;
                font-size: 14px;
                selection-background-color: #8A2BE2;
            }
            QLineEdit:focus {
                border-bottom: 2px solid #8A2BE2;
            }
            QPushButton#activateBtn {
                background-color: #8A2BE2;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#activateBtn:hover {
                background-color: #9D50EC;
            }
            QPushButton#purchaseBtn {
                color: #8A2BE2;
                background: transparent;
                border: none;
                text-decoration: underline;
                font-size: 13px;
            }
            QPushButton#purchaseBtn:hover {
                color: #9D50EC;
            }
        """)
        
        self.db_manager = DatabaseManager()
        self.db_manager.connect()
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 30, 50, 30)
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("AUTO Hekili")
        title_label.setStyleSheet("font-size: 40px; font-weight: bold; color: #FFD100;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Subtitle
        subtitle_label = QLabel("License Required")
        subtitle_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #8A2BE2;")
        subtitle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle_label)
        
        # Add some space
        layout.addSpacing(5)
        
        # Description
        desc_label = QLabel("To use AUTO_Hekili, you need to activate a valid license key. "
                           "If you already have a key, you can activate it now.")
        desc_label.setStyleSheet("color: #DDDDDD; font-size: 13px;")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # Add some space
        layout.addSpacing(30)
        
        # License key input
        self.license_input = QLineEdit()
        self.license_input.setPlaceholderText("Enter your license key here")
        self.license_input.setMinimumWidth(400)
        self.license_input.setFixedHeight(30)
        self.license_input.setAlignment(Qt.AlignCenter)
        input_layout = QHBoxLayout()
        input_layout.addStretch()
        input_layout.addWidget(self.license_input)
        input_layout.addStretch()
        layout.addLayout(input_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888888; font-size: 13px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Add some space
        layout.addSpacing(30)
        
        # Activate button
        self.activate_btn = QPushButton("Activate License")
        self.activate_btn.setObjectName("activateBtn")
        self.activate_btn.setFixedWidth(200)
        self.activate_btn.setFixedHeight(45)
        self.activate_btn.clicked.connect(self.activate_license)
        
        # Center the button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.activate_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Add space
        layout.addSpacing(20)
        
        # Purchase text
        purchase_layout = QHBoxLayout()
        purchase_layout.addStretch()
        purchase_label = QLabel("Don't have a license yet?")
        purchase_label.setStyleSheet("color: #888888; font-size: 13px;")
        purchase_layout.addWidget(purchase_label)
        
        purchase_btn = QPushButton("Purchase one now")
        purchase_btn.setObjectName("purchaseBtn")
        purchase_btn.clicked.connect(self.open_purchase_page)
        purchase_layout.addWidget(purchase_btn)
        purchase_layout.addStretch()
        layout.addLayout(purchase_layout)
        
        # Add a stretch at the end to push everything up a bit
        layout.addStretch()
    
    def activate_license(self):
        license_key = self.license_input.text().strip()
        
        if not license_key:
            self.status_label.setText("Please enter a license key")
            self.status_label.setStyleSheet("color: #FF5555;")
            return
        
        self.status_label.setText("Validating license...")
        self.status_label.setStyleSheet("color: #55AAFF;")
        QApplication.processEvents()  # Update UI immediately
        
        # Generate hardware ID
        hardware_id = generate_hardware_id()
        
        # Check if hardware is banned before proceeding
        is_banned, ban_reason = self.db_manager.check_hardware_ban(hardware_id)
        if is_banned:
            logging.warning(f"Hardware banned during activation! Reason: {ban_reason}")
            ban_dialog = HardwareBanDialog(ban_reason, hardware_id)
            ban_dialog.exec_()
            self.reject()  # Close activation window
            return
        
        client_info = f"AUTO_Hekili v1.0, OS: {platform.system()} {platform.release()}"
        
        # First check if the license is valid
        if self.db_manager.validate_license(license_key):
            # Activate the license for this hardware
            if self.db_manager.activate_license(license_key, hardware_id, client_info):
                self.save_license(license_key, hardware_id)
                QMessageBox.information(self, "Success", "License activated successfully!")
                self.accept()
            else:
                self.status_label.setText("License already in use on maximum allowed devices")
                self.status_label.setStyleSheet("color: #FF5555;")
                QMessageBox.warning(self, "Activation Failed", 
                                   "This license is already activated on the maximum number of devices.")
        else:
            self.status_label.setText("Invalid license key")
            self.status_label.setStyleSheet("color: #FF5555;")
            QMessageBox.warning(self, "Activation Failed", "The license key you entered is not valid.")
    
    def open_purchase_page(self):
        """Opens the web page for purchasing a license using Sell.app"""
        sell_app_html = """<!DOCTYPE html>
<html>
<head>
    <title>Purchase AUTO_Hekili License</title>
    <link href="https://cdn.sell.app/embed/style.css" rel="stylesheet" />
    <style>
        body {
            background-color: #121212;
            color: white;
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            padding: 20px;
            text-align: center;
        }
        h1 {
            background: linear-gradient(to right, #FFD100, #FFB000);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        h2 {
            color: #8A2BE2;
            font-size: 1.8em;
            margin-bottom: 20px;
        }
        p {
            color: #CCCCCC;
            margin-bottom: 30px;
            max-width: 600px;
            line-height: 1.6;
        }
        .purchase-container {
            background-color: #1D1D1D;
            padding: 30px;
            border-radius: 10px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <h1>AUTO Hekili</h1>
    <h2>Purchase License</h2>
    <p>
        Get instant access to AUTO_Hekili with your license purchase. 
        All sales are final and no refunds will be provided.
    </p>
    
    <div class="purchase-container">
        <button
            data-sell-store="56234"
            data-sell-product="292922"
            data-sell-darkmode="true"
            data-sell-theme=""
            style="background: linear-gradient(to right, #00b4d8, #0077b6); padding: 12px 24px; font-size: 16px; border: none; border-radius: 6px; color: white; font-weight: bold; cursor: pointer;"
        >
            Complete Purchase
        </button>
    </div>

    <script src="https://cdn.sell.app/embed/script.js" type="module"></script>
</body>
</html>"""
        
        # Save to temporary file and open in browser
        fd, path = tempfile.mkstemp(suffix='.html')
        with os.fdopen(fd, 'w') as f:
            f.write(sell_app_html)
        
        webbrowser.open(f'file://{path}')
    
    def save_license(self, license_key, hardware_id):
        """Save license data for offline use."""
        # Retrieve expiration date from database
        expiration_date = None
        try:
            if self.db_manager.connection and self.db_manager.connection.is_connected():
                cursor = self.db_manager.connection.cursor(dictionary=True)
                cursor.execute(
                    "SELECT expiration_date FROM licenses WHERE license_key = %s",
                    (license_key,)
                )
                result = cursor.fetchone()
                if result and result['expiration_date']:
                    expiration_date = result['expiration_date'].isoformat()
                cursor.close()
        except Exception as e:
            logging.error(f"Error retrieving expiration date: {e}")
        
        # Create license data
        license_data = {
            "license_key": license_key,
            "hardware_id": hardware_id,
            "activation_date": datetime.datetime.now().isoformat(),
            "status": "active",
            "expiration_date": expiration_date
        }
    
        # Save to file - FIXED INDENTATION HERE
        os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)
        with open(LICENSE_FILE, 'w') as f:
            json.dump(license_data, f, indent=4)
        
        logging.info(f"Saved license data for key: {license_key}")
    
    def closeEvent(self, event):
        """Close database connection when window is closed."""
        self.db_manager.disconnect()
        super().closeEvent(event)

def load_license_file():
    """Load license data from file if it exists."""
    try:
        if os.path.exists(LICENSE_FILE):
            logging.info(f"Loading license from {LICENSE_FILE}")
            with open(LICENSE_FILE, 'r') as f:
                return json.load(f)
        return None
    except Exception as e:
        logging.error(f"Error loading license: {e}")
        return None

def verify_license(license_data):
    """Verify a previously saved license is still valid."""
    if not license_data:
        return False
        
    license_key = license_data.get("license_key")
    hardware_id = license_data.get("hardware_id")
    
    if not license_key or not hardware_id:
        return False
    
    # First check if hardware ID still matches
    current_hw_id = generate_hardware_id()
    if current_hw_id != hardware_id:
        logging.warning(f"Hardware ID mismatch. Saved: {hardware_id}, Current: {current_hw_id}")
        return False
    
    # Then validate with database
    db_manager = DatabaseManager()
    if not db_manager.connect():
        # In offline mode, just check against hardcoded keys
        result = license_key in VALID_LICENSE_KEYS
        db_manager.disconnect()
        return result
    
    # Check license validity
    valid = db_manager.validate_license(license_key)
    
    # Update last verification if valid
    if valid:
        client_info = f"AUTO_Hekili v1.0, OS: {platform.system()} {platform.release()}"
        db_manager.activate_license(license_key, hardware_id, client_info)
        
    db_manager.disconnect()
    return valid

def generate_hardware_id():
    """Generate a unique hardware ID for this system."""
    system_info = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        str(uuid.getnode())  # MAC address
    ]
    hw_string = ":".join(system_info)
    return hashlib.sha256(hw_string.encode()).hexdigest()[:32]

def launch_main_application(app):
    """Launch the main application after license validation."""
    try:
        from auto_hekili_console import AutoHekiliGUI
        main_window = AutoHekiliGUI()
        main_window.show()
        logging.info("Main window displayed, entering application event loop")
        sys.exit(app.exec_())
    except Exception as e:
        logging.error(f"Error launching main application: {str(e)}")
        logging.error(traceback.format_exc())
        QMessageBox.critical(None, "Application Error", 
                           f"Error launching main application:\n{str(e)}")

def main():
    """Main entry point that shows license UI first."""
    try:
        logging.info("====== APPLICATION STARTING ======")
        print("Application starting...")
        
        # Ensure required directories exist
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        os.makedirs(DEBUG_DIR, exist_ok=True)
        
        # Create QApplication first
        app = QApplication(sys.argv)
        
        # Check for hardware ban first (critical check)
        hardware_id = generate_hardware_id()
        logging.info(f"Generated hardware ID: {hardware_id}")
        
        db_manager = DatabaseManager()
        db_manager.connect()
        is_banned, ban_reason = db_manager.check_hardware_ban(hardware_id)
        
        if is_banned:
            logging.warning(f"Hardware banned! Reason: {ban_reason}")
            ban_dialog = HardwareBanDialog(ban_reason, hardware_id)
            ban_dialog.exec_()
            db_manager.disconnect()
            return  # Exit application
            
        # If hardware not banned, continue with license check
        # Check if we already have a valid license file
        license_data = load_license_file()
        if license_data and verify_license(license_data):
            # Double-check hardware ban again to be sure
            is_banned, ban_reason = db_manager.check_hardware_ban(hardware_id)
            if is_banned:
                logging.warning(f"Hardware banned during verification! Reason: {ban_reason}")
                ban_dialog = HardwareBanDialog(ban_reason, hardware_id)
                ban_dialog.exec_()
                db_manager.disconnect()
                return  # Exit application
                
            logging.info("Found valid license file, launching main application")
            print("License is valid, launching main application...")
            db_manager.disconnect()
            launch_main_application(app)
        else:
            # No valid license, show activation window
            db_manager.disconnect()
            license_window = LicenseWindow()
            if license_window.exec_() == QDialog.Accepted:
                # After activation, check hardware ban once more before launching
                db_manager = DatabaseManager()
                db_manager.connect()
                is_banned, ban_reason = db_manager.check_hardware_ban(hardware_id)
                
                if is_banned:
                    logging.warning(f"Hardware banned after activation! Reason: {ban_reason}")
                    ban_dialog = HardwareBanDialog(ban_reason, hardware_id)
                    ban_dialog.exec_()
                    db_manager.disconnect()
                    return  # Exit application
                
                # User entered a valid license, now launch the main app
                db_manager.disconnect()
                launch_main_application(app)
            else:
                logging.info("User canceled license activation")
                print("User canceled license activation")
            
    except Exception as e:
        logging.critical(f"Unhandled exception in main: {str(e)}")
        logging.critical(traceback.format_exc())
        QMessageBox.critical(None, "Critical Error", f"Unhandled exception:\n{str(e)}")

if __name__ == "__main__":
    logging.debug("Script executed directly")
    main()