import sys
import os
import uuid
import datetime
import hashlib
import mysql.connector
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QLabel, QPushButton, QLineEdit, QComboBox, QTableWidget, 
                           QTableWidgetItem, QTabWidget, QMessageBox, QGroupBox,
                           QFormLayout, QDateEdit, QTextEdit, QCheckBox, QHeaderView,
                           QSplitter, QDialog, QDialogButtonBox, QSpinBox, QInputDialog)
from PyQt5.QtCore import Qt, QDate, QDateTime
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette

# Database configuration
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "ascent",
    "port": 3306,
    "database": "auto_hekili_licenses"
}

# Colors for styling
DARK_BLUE = "#0F1929"
MEDIUM_BLUE = "#192742"
LIGHT_BLUE = "#344E7F"
GOLD = "#FFD100"
PURPLE = "#6A22EF"
RED = "#E64A19"
GREEN = "#2E7D32"

class DBConnection:
    """Database connection manager with context support."""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        self.conn = mysql.connector.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor(dictionary=True)
        return self.cursor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn and self.cursor:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
            self.cursor.close()
            self.conn.close()

class LoginDialog(QDialog):
    """Admin login dialog."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin Login")
        self.setFixedSize(400, 200)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Username and password fields
        form_layout = QFormLayout()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        
        form_layout.addRow("Username:", self.username_input)
        form_layout.addRow("Password:", self.password_input)
        
        layout.addLayout(form_layout)
        
        # Login button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.validate_login)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
        
        # Set focus on username
        self.username_input.setFocus()
    
    def validate_login(self):
        """Validate admin credentials."""
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter both username and password")
            return
        
        # Hash the password for comparison
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        try:
            with DBConnection() as cursor:
                cursor.execute(
                    "SELECT * FROM admin_users WHERE username = %s AND is_active = TRUE",
                    (username,)
                )
                user = cursor.fetchone()
                
                if user and user['password_hash'] == password_hash:
                    # Update last login
                    cursor.execute(
                        "UPDATE admin_users SET last_login = NOW() WHERE id = %s",
                        (user['id'],)
                    )
                    self.accept()
                else:
                    QMessageBox.warning(self, "Error", "Invalid username or password")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Error connecting to database: {str(e)}")

class GenerateLicenseDialog(QDialog):
    """Dialog for generating new license keys."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate License Keys")
        self.setFixedSize(500, 400)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Form for license key parameters
        form_box = QGroupBox("License Parameters")
        form_layout = QFormLayout()
        
        # Number of keys
        self.key_count = QSpinBox()
        self.key_count.setMinimum(1)
        self.key_count.setMaximum(100)
        self.key_count.setValue(1)
        form_layout.addRow("Number of keys:", self.key_count)
        
        # Expiration date
        self.expiration_date = QDateEdit()
        self.expiration_date.setDate(QDate.currentDate().addMonths(1))
        self.expiration_date.setCalendarPopup(True)
        form_layout.addRow("Expiration date:", self.expiration_date)
        
        # Notes
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Enter optional notes about these license keys")
        form_layout.addRow("Notes:", self.notes_input)
        
        form_box.setLayout(form_layout)
        layout.addWidget(form_box)
        
        # Generated keys display
        keys_box = QGroupBox("Generated Keys")
        keys_layout = QVBoxLayout()
        
        self.keys_display = QTextEdit()
        self.keys_display.setReadOnly(True)
        self.keys_display.setPlaceholderText("Generated keys will appear here")
        
        keys_layout.addWidget(self.keys_display)
        keys_box.setLayout(keys_layout)
        layout.addWidget(keys_box)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("Generate Keys")
        self.generate_btn.clicked.connect(self.generate_keys)
        
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(self.generate_btn)
        button_layout.addWidget(self.copy_btn)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
    
    def generate_keys(self):
        """Generate new license keys and store them in the database."""
        try:
            count = self.key_count.value()
            expiration_date = self.expiration_date.date().toPyDate()
            notes = self.notes_input.toPlainText()
            
            # Format expiration date for MySQL
            expiration_str = expiration_date.strftime("%Y-%m-%d 23:59:59")
            
            generated_keys = []
            with DBConnection() as cursor:
                for _ in range(count):
                    # Generate a unique key
                    license_key = str(uuid.uuid4()).upper()
                    
                    # Insert into database
                    cursor.execute(
                        """INSERT INTO licenses 
                           (license_key, status, expiration_date, notes) 
                           VALUES (%s, 'active', %s, %s)""",
                        (license_key, expiration_str, notes)
                    )
                    
                    generated_keys.append(license_key)
            
            # Display generated keys
            self.keys_display.setPlainText("\n".join(generated_keys))
            self.copy_btn.setEnabled(True)
            
            QMessageBox.information(
                self, 
                "Success", 
                f"Successfully generated {count} license key(s)"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"Error generating license keys: {str(e)}"
            )
    
    def copy_to_clipboard(self):
        """Copy generated keys to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.keys_display.toPlainText())
        QMessageBox.information(self, "Copied", "Keys copied to clipboard")

class AdminPanel(QMainWindow):
    """Main admin panel window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUTO_Hekili License Admin Panel")
        self.setGeometry(100, 100, 1200, 800)
        self.setup_ui()
        
        # Refresh data initially
        self.refresh_all_data()
    
    def setup_ui(self):
        """Set up the admin panel UI."""
        # Set dark theme
        self.set_dark_theme()
        
        # Main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("AUTO_Hekili License Management")
        title_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {GOLD};")
        
        refresh_btn = QPushButton("Refresh All Data")
        refresh_btn.clicked.connect(self.refresh_all_data)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(refresh_btn)
        
        main_layout.addLayout(header_layout)
        
        # Tab widget for different sections
        self.tabs = QTabWidget()
        
        # Create tabs
        self.create_licenses_tab()
        self.create_hardware_tab()
        self.create_activations_tab()
        self.create_attempts_tab()
        
        main_layout.addWidget(self.tabs)
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def set_dark_theme(self):
        """Apply dark theme styling to the application."""
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {DARK_BLUE};
                color: {GOLD};
            }}
            
            QTabWidget::pane {{
                border: 1px solid {LIGHT_BLUE};
                border-radius: 3px;
                top: -1px;
                background-color: {DARK_BLUE};
            }}
            
            QTabBar::tab {{
                background-color: {MEDIUM_BLUE};
                color: {GOLD};
                border: 1px solid {LIGHT_BLUE};
                border-bottom-color: {MEDIUM_BLUE};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                min-width: 120px;
                padding: 8px 12px;
                font-weight: bold;
                margin-right: 4px;
            }}
            
            QTabBar::tab:selected {{
                background-color: {LIGHT_BLUE};
                border-bottom-color: {LIGHT_BLUE};
            }}
            
            QPushButton {{
                background-color: {LIGHT_BLUE};
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 3px;
                padding: 8px 12px;
                min-height: 24px;
                min-width: 80px;
            }}
            
            QPushButton:hover {{
                background-color: #4A6EA5;
            }}
            
            QPushButton:pressed {{
                background-color: #263A5E;
            }}
            
            QPushButton#danger {{
                background-color: {RED};
            }}
            
            QPushButton#danger:hover {{
                background-color: #FF5722;
            }}
            
            QPushButton#success {{
                background-color: {GREEN};
            }}
            
            QPushButton#success:hover {{
                background-color: #43A047;
            }}
            
            QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox {{
                background-color: {MEDIUM_BLUE};
                border: 1px solid {LIGHT_BLUE};
                border-radius: 3px;
                padding: 5px;
                color: white;
                font-weight: bold;
                selection-background-color: {LIGHT_BLUE};
            }}
            
            QTableWidget {{
                background-color: {MEDIUM_BLUE};
                color: white;
                gridline-color: {LIGHT_BLUE};
                border: 1px solid {LIGHT_BLUE};
                border-radius: 3px;
            }}
            
            QTableWidget::item {{
                border-bottom: 1px solid {LIGHT_BLUE};
                padding: 5px;
            }}
            
            QTableWidget::item:selected {{
                background-color: {LIGHT_BLUE};
                color: white;
            }}
            
            QHeaderView::section {{
                background-color: {LIGHT_BLUE};
                color: white;
                padding: 5px;
                border: 1px solid {DARK_BLUE};
                font-weight: bold;
            }}
            
            QGroupBox {{
                border: 1px solid {LIGHT_BLUE};
                border-radius: 5px;
                margin-top: 15px;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 10px;
                color: {GOLD};
                background-color: {DARK_BLUE};
            }}
            
            QStatusBar {{
                background-color: {MEDIUM_BLUE};
                color: white;
            }}
            
            /* Fix for button containers in table cells */
            QWidget[actionContainer="true"] {{
                min-width: 300px;
                max-width: 300px;
                padding: 2px;
            }}
            
            /* Style for action buttons in tables */
            QPushButton[actionButton="true"] {{
                min-width: 85px;
                min-height: 28px;
                margin: 2px 3px;
            }}
        """)
    
    def create_licenses_tab(self):
        """Create the licenses management tab."""
        licenses_tab = QWidget()
        layout = QVBoxLayout(licenses_tab)
        
        # Controls group
        controls_box = QGroupBox("License Controls")
        controls_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("Generate New License Keys")
        self.generate_btn.clicked.connect(self.show_generate_dialog)
        
        self.license_filter = QComboBox()
        self.license_filter.addItems(["All", "Active", "Expired", "Banned", "Inactive"])
        self.license_filter.currentTextChanged.connect(self.refresh_licenses)
        
        controls_layout.addWidget(self.generate_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(QLabel("Filter:"))
        controls_layout.addWidget(self.license_filter)
        
        controls_box.setLayout(controls_layout)
        layout.addWidget(controls_box)
        
        # Licenses table
        self.licenses_table = QTableWidget()
        self.licenses_table.setColumnCount(7)
        self.licenses_table.setHorizontalHeaderLabels([
            "License Key", "Status", "Created", "Expires", "Activations", "Notes", "Actions"
        ])
        
        # Set column resize modes - Actions column gets more space
        self.licenses_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.licenses_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        
        self.licenses_table.verticalHeader().setVisible(False)
        self.licenses_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.licenses_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.licenses_table)
        
        self.tabs.addTab(licenses_tab, "License Keys")
    
    def create_hardware_tab(self):
        """Create the hardware IDs management tab."""
        hardware_tab = QWidget()
        layout = QVBoxLayout(hardware_tab)
        
        # Controls group
        controls_box = QGroupBox("Hardware Controls")
        controls_layout = QHBoxLayout()
        
        self.hardware_filter = QComboBox()
        self.hardware_filter.addItems(["All", "Active", "Banned"])
        self.hardware_filter.currentTextChanged.connect(self.refresh_hardware)
        
        controls_layout.addStretch()
        controls_layout.addWidget(QLabel("Filter:"))
        controls_layout.addWidget(self.hardware_filter)
        
        controls_box.setLayout(controls_layout)
        layout.addWidget(controls_box)
        
        # Hardware table
        self.hardware_table = QTableWidget()
        self.hardware_table.setColumnCount(6)
        self.hardware_table.setHorizontalHeaderLabels([
            "Hardware ID", "Status", "First Seen", "Activations", "Ban Reason", "Actions"
        ])
        
        # Set column resize modes - Actions column gets more space
        self.hardware_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hardware_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        self.hardware_table.verticalHeader().setVisible(False)
        self.hardware_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.hardware_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.hardware_table)
        
        self.tabs.addTab(hardware_tab, "Hardware IDs")
    
    def create_activations_tab(self):
        """Create the activations management tab."""
        activations_tab = QWidget()
        layout = QVBoxLayout(activations_tab)
        
        # Activations table
        self.activations_table = QTableWidget()
        self.activations_table.setColumnCount(7)
        self.activations_table.setHorizontalHeaderLabels([
            "License Key", "Hardware ID", "Activated On", "Last Verification",
            "Legitimate", "License Status", "Actions"
        ])
        
        # Set column resize modes - Actions column gets more space
        self.activations_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.activations_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        
        self.activations_table.verticalHeader().setVisible(False)
        self.activations_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.activations_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.activations_table)
        
        self.tabs.addTab(activations_tab, "Activations")
    
    def create_attempts_tab(self):
        """Create the login attempts tab."""
        attempts_tab = QWidget()
        layout = QVBoxLayout(attempts_tab)
        
        # Controls group
        controls_box = QGroupBox("Filter Login Attempts")
        controls_layout = QHBoxLayout()
        
        self.attempt_filter = QComboBox()
        self.attempt_filter.addItems(["All", "Successful", "Failed"])
        self.attempt_filter.currentTextChanged.connect(self.refresh_attempts)
        
        self.limit_combo = QComboBox()
        self.limit_combo.addItems(["50 entries", "100 entries", "200 entries", "500 entries"])
        self.limit_combo.currentTextChanged.connect(self.refresh_attempts)
        
        controls_layout.addStretch()
        controls_layout.addWidget(QLabel("Show:"))
        controls_layout.addWidget(self.attempt_filter)
        controls_layout.addWidget(QLabel("Limit:"))
        controls_layout.addWidget(self.limit_combo)
        
        controls_box.setLayout(controls_layout)
        layout.addWidget(controls_box)
        
        # Attempts table
        self.attempts_table = QTableWidget()
        self.attempts_table.setColumnCount(6)
        self.attempts_table.setHorizontalHeaderLabels([
            "Timestamp", "License Key", "Hardware ID", "Success", "IP Address", "Client Info"
        ])
        self.attempts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.attempts_table.verticalHeader().setVisible(False)
        self.attempts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.attempts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.attempts_table)
        
        self.tabs.addTab(attempts_tab, "Login Attempts")
    
    def refresh_all_data(self):
        """Refresh all data in all tabs."""
        self.refresh_licenses()
        self.refresh_hardware()
        self.refresh_activations()
        self.refresh_attempts()
        self.statusBar().showMessage("Data refreshed at " + datetime.datetime.now().strftime("%H:%M:%S"))
    
    def refresh_licenses(self):
        """Refresh the licenses table."""
        try:
            self.licenses_table.setRowCount(0)
            
            filter_status = self.license_filter.currentText()
            with DBConnection() as cursor:
                if filter_status == "All":
                    cursor.execute("SELECT * FROM licenses ORDER BY creation_date DESC")
                else:
                    cursor.execute(
                        "SELECT * FROM licenses WHERE status = %s ORDER BY creation_date DESC",
                        (filter_status.lower(),)
                    )
                
                licenses = cursor.fetchall()
                
                for row, license_data in enumerate(licenses):
                    self.licenses_table.insertRow(row)
                    
                    # Get activation count
                    cursor.execute(
                        "SELECT COUNT(*) as count FROM activations WHERE license_key = %s",
                        (license_data['license_key'],)
                    )
                    activation_count = cursor.fetchone()['count']
                    
                    # Format dates
                    created = license_data['creation_date'].strftime("%Y-%m-%d") if license_data['creation_date'] else ""
                    expires = license_data['expiration_date'].strftime("%Y-%m-%d") if license_data['expiration_date'] else "Never"
                    
                    # Add data to table
                    self.licenses_table.setItem(row, 0, QTableWidgetItem(license_data['license_key']))
                    
                    status_item = QTableWidgetItem(license_data['status'].capitalize())
                    if license_data['status'] == 'active':
                        status_item.setForeground(QColor(GREEN))
                    elif license_data['status'] == 'banned':
                        status_item.setForeground(QColor(RED))
                    self.licenses_table.setItem(row, 1, status_item)
                    
                    self.licenses_table.setItem(row, 2, QTableWidgetItem(created))
                    self.licenses_table.setItem(row, 3, QTableWidgetItem(expires))
                    self.licenses_table.setItem(row, 4, QTableWidgetItem(str(activation_count)))
                    self.licenses_table.setItem(row, 5, QTableWidgetItem(license_data['notes'] or ""))
                    
                    # Actions - with improved layout
                    action_widget = QWidget()
                    action_widget.setProperty("actionContainer", True)
                    action_layout = QHBoxLayout(action_widget)
                    action_layout.setContentsMargins(5, 2, 5, 2)
                    action_layout.setSpacing(5)
                    
                    # Dynamic buttons based on current status
                    if license_data['status'] == 'active':
                        # Ban button
                        ban_btn = QPushButton("Ban")
                        ban_btn.setObjectName("danger")
                        ban_btn.setProperty("actionButton", True)
                        ban_btn.clicked.connect(lambda _, key=license_data['license_key']: self.ban_license(key))
                        action_layout.addWidget(ban_btn)
                        
                        # Deactivate button
                        deactivate_btn = QPushButton("Deactivate")
                        deactivate_btn.setProperty("actionButton", True)
                        deactivate_btn.clicked.connect(lambda _, key=license_data['license_key']: self.deactivate_license(key))
                        action_layout.addWidget(deactivate_btn)
                    elif license_data['status'] == 'banned':
                        # Unban button
                        unban_btn = QPushButton("Unban")
                        unban_btn.setObjectName("success")
                        unban_btn.setProperty("actionButton", True)
                        unban_btn.clicked.connect(lambda _, key=license_data['license_key']: self.unban_license(key))
                        action_layout.addWidget(unban_btn)
                    elif license_data['status'] == 'inactive':
                        # Activate button
                        activate_btn = QPushButton("Activate")
                        activate_btn.setObjectName("success")
                        activate_btn.setProperty("actionButton", True)
                        activate_btn.clicked.connect(lambda _, key=license_data['license_key']: self.activate_license(key))
                        action_layout.addWidget(activate_btn)
                    
                    # View details button
                    details_btn = QPushButton("Details")
                    details_btn.setProperty("actionButton", True)
                    details_btn.clicked.connect(lambda _, key=license_data['license_key']: self.view_license_details(key))
                    action_layout.addWidget(details_btn)
                    
                    self.licenses_table.setCellWidget(row, 6, action_widget)
                
                # Adjust row heights for better button display
                for i in range(self.licenses_table.rowCount()):
                    self.licenses_table.setRowHeight(i, 55)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error refreshing licenses: {str(e)}")

    
    def refresh_hardware(self):
        """Refresh the hardware table."""
        try:
            self.hardware_table.setRowCount(0)
            
            filter_status = self.hardware_filter.currentText()
            with DBConnection() as cursor:
                if filter_status == "All":
                    cursor.execute("SELECT * FROM hardware_ids ORDER BY first_seen DESC")
                else:
                    cursor.execute(
                        "SELECT * FROM hardware_ids WHERE status = %s ORDER BY first_seen DESC",
                        (filter_status.lower(),)
                    )
                
                hardware_ids = cursor.fetchall()
                
                for row, hw_data in enumerate(hardware_ids):
                    self.hardware_table.insertRow(row)
                    
                    # Get activation count
                    cursor.execute(
                        "SELECT COUNT(*) as count FROM activations WHERE hardware_id = %s",
                        (hw_data['hardware_id'],)
                    )
                    activation_count = cursor.fetchone()['count']
                    
                    # Format dates
                    first_seen = hw_data['first_seen'].strftime("%Y-%m-%d") if hw_data['first_seen'] else ""
                    
                    # Add data to table
                    self.hardware_table.setItem(row, 0, QTableWidgetItem(hw_data['hardware_id']))
                    
                    status_item = QTableWidgetItem(hw_data['status'].capitalize())
                    if hw_data['status'] == 'active':
                        status_item.setForeground(QColor(GREEN))
                    elif hw_data['status'] == 'banned':
                        status_item.setForeground(QColor(RED))
                    self.hardware_table.setItem(row, 1, status_item)
                    
                    self.hardware_table.setItem(row, 2, QTableWidgetItem(first_seen))
                    self.hardware_table.setItem(row, 3, QTableWidgetItem(str(activation_count)))
                    self.hardware_table.setItem(row, 4, QTableWidgetItem(hw_data['ban_reason'] or ""))
                    
                    # Actions - with improved layout
                    action_widget = QWidget()
                    action_widget.setProperty("actionContainer", True)
                    action_layout = QHBoxLayout(action_widget)
                    action_layout.setContentsMargins(5, 2, 5, 2)
                    action_layout.setSpacing(5)
                    
                    # Dynamic buttons based on current status
                    if hw_data['status'] == 'active':
                        # Ban button
                        ban_btn = QPushButton("Ban")
                        ban_btn.setObjectName("danger")
                        ban_btn.setProperty("actionButton", True)
                        ban_btn.clicked.connect(lambda _, hw=hw_data['hardware_id']: self.ban_hardware(hw))
                        action_layout.addWidget(ban_btn)
                    elif hw_data['status'] == 'banned':
                        # Unban button
                        unban_btn = QPushButton("Unban")
                        unban_btn.setObjectName("success")
                        unban_btn.setProperty("actionButton", True)
                        unban_btn.clicked.connect(lambda _, hw=hw_data['hardware_id']: self.unban_hardware(hw))
                        action_layout.addWidget(unban_btn)
                    
                    # View details button
                    details_btn = QPushButton("Details")
                    details_btn.setProperty("actionButton", True)
                    details_btn.clicked.connect(lambda _, hw=hw_data['hardware_id']: self.view_hardware_details(hw))
                    action_layout.addWidget(details_btn)
                    
                    self.hardware_table.setCellWidget(row, 5, action_widget)
                
                # Adjust row heights for better button display
                for i in range(self.hardware_table.rowCount()):
                    self.hardware_table.setRowHeight(i, 55)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error refreshing hardware data: {str(e)}")


    
    
    def refresh_activations(self):
        """Refresh the activations table."""
        try:
            self.activations_table.setRowCount(0)
            
            with DBConnection() as cursor:
                cursor.execute("""
                    SELECT a.*, l.status as license_status
                    FROM activations a
                    JOIN licenses l ON a.license_key = l.license_key
                    ORDER BY a.activation_date DESC
                """)
                
                activations = cursor.fetchall()
                
                for row, activation in enumerate(activations):
                    self.activations_table.insertRow(row)
                    
                    # Format dates
                    activated = activation['activation_date'].strftime("%Y-%m-%d %H:%M") if activation['activation_date'] else ""
                    last_verified = activation['last_verification'].strftime("%Y-%m-%d %H:%M") if activation['last_verification'] else ""
                    
                    # Add data to table
                    self.activations_table.setItem(row, 0, QTableWidgetItem(activation['license_key']))
                    self.activations_table.setItem(row, 1, QTableWidgetItem(activation['hardware_id']))
                    self.activations_table.setItem(row, 2, QTableWidgetItem(activated))
                    self.activations_table.setItem(row, 3, QTableWidgetItem(last_verified))
                    
                    # Legitimate flag
                    legitimate_item = QTableWidgetItem("Yes" if activation['is_legitimate'] else "No")
                    if activation['is_legitimate']:
                        legitimate_item.setForeground(QColor(GREEN))
                    else:
                        legitimate_item.setForeground(QColor(RED))
                    self.activations_table.setItem(row, 4, legitimate_item)
                    
                    # License status
                    status_item = QTableWidgetItem(activation['license_status'].capitalize())
                    if activation['license_status'] == 'active':
                        status_item.setForeground(QColor(GREEN))
                    elif activation['license_status'] == 'banned':
                        status_item.setForeground(QColor(RED))
                    self.activations_table.setItem(row, 5, status_item)
                    
                    # Actions - with improved layout
                    action_widget = QWidget()
                    action_layout = QHBoxLayout(action_widget)
                    action_layout.setContentsMargins(4, 4, 4, 4)
                    action_layout.setSpacing(8)
                    
                    # Delete activation button
                    delete_btn = QPushButton("Delete")
                    delete_btn.setObjectName("danger")
                    delete_btn.setFixedHeight(30)
                    delete_btn.clicked.connect(lambda _, key=activation['license_key'], hw=activation['hardware_id']: 
                                             self.delete_activation(key, hw))
                    action_layout.addWidget(delete_btn)
                    
                    # Toggle legitimacy button
                    if activation['is_legitimate']:
                        mark_btn = QPushButton("Mark Illegitimate")
                        mark_btn.setFixedHeight(30)
                        mark_btn.clicked.connect(lambda _, key=activation['license_key'], hw=activation['hardware_id']: 
                                               self.toggle_legitimacy(key, hw, False))
                    else:
                        mark_btn = QPushButton("Mark Legitimate")
                        mark_btn.setObjectName("success")
                        mark_btn.setFixedHeight(30)
                        mark_btn.clicked.connect(lambda _, key=activation['license_key'], hw=activation['hardware_id']: 
                                               self.toggle_legitimacy(key, hw, True))
                    action_layout.addWidget(mark_btn)
                    
                    self.activations_table.setCellWidget(row, 6, action_widget)
                
                # Adjust row heights for better button display
                for i in range(self.activations_table.rowCount()):
                    self.activations_table.setRowHeight(i, 55)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error refreshing activations: {str(e)}")
    
    def refresh_attempts(self):
        """Refresh the login attempts table."""
        try:
            self.attempts_table.setRowCount(0)
            
            filter_status = self.attempt_filter.currentText()
            limit_text = self.limit_combo.currentText()
            limit = int(limit_text.split()[0])  # Extract number from "X entries"
            
            with DBConnection() as cursor:
                if filter_status == "All":
                    cursor.execute(
                        "SELECT * FROM login_attempts ORDER BY timestamp DESC LIMIT %s",
                        (limit,)
                    )
                elif filter_status == "Successful":
                    cursor.execute(
                        "SELECT * FROM login_attempts WHERE success = TRUE ORDER BY timestamp DESC LIMIT %s",
                        (limit,)
                    )
                else:  # Failed
                    cursor.execute(
                        "SELECT * FROM login_attempts WHERE success = FALSE ORDER BY timestamp DESC LIMIT %s",
                        (limit,)
                    )
                
                attempts = cursor.fetchall()
                
                for row, attempt in enumerate(attempts):
                    self.attempts_table.insertRow(row)
                    
                    # Format timestamp
                    timestamp = attempt['timestamp'].strftime("%Y-%m-%d %H:%M:%S") if attempt['timestamp'] else ""
                    
                    # Add data to table
                    self.attempts_table.setItem(row, 0, QTableWidgetItem(timestamp))
                    self.attempts_table.setItem(row, 1, QTableWidgetItem(attempt['license_key']))
                    self.attempts_table.setItem(row, 2, QTableWidgetItem(attempt['hardware_id']))
                    
                    # Success status
                    success_item = QTableWidgetItem("Yes" if attempt['success'] else "No")
                    if attempt['success']:
                        success_item.setForeground(QColor(GREEN))
                    else:
                        success_item.setForeground(QColor(RED))
                    self.attempts_table.setItem(row, 3, success_item)
                    
                    self.attempts_table.setItem(row, 4, QTableWidgetItem(attempt['ip_address'] or ""))
                    self.attempts_table.setItem(row, 5, QTableWidgetItem(attempt['client_info'] or ""))
                
                # Adjust row heights
                for i in range(self.attempts_table.rowCount()):
                    self.attempts_table.setRowHeight(i, 55)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error refreshing login attempts: {str(e)}")
    
    def show_generate_dialog(self):
        """Show dialog to generate new license keys."""
        dialog = GenerateLicenseDialog(self)
        dialog.exec_()
        self.refresh_licenses()
    
    def ban_license(self, license_key):
        """Ban a license key."""
        reply = QMessageBox.question(
            self, 
            "Confirm Ban", 
            f"Are you sure you want to ban the license key: {license_key}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                with DBConnection() as cursor:
                    cursor.execute(
                        "UPDATE licenses SET status = 'banned' WHERE license_key = %s",
                        (license_key,)
                    )
                self.refresh_licenses()
                QMessageBox.information(self, "Success", "License banned successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error banning license: {str(e)}")
    
    def unban_license(self, license_key):
        """Unban a license key."""
        try:
            with DBConnection() as cursor:
                cursor.execute(
                    "UPDATE licenses SET status = 'active' WHERE license_key = %s",
                    (license_key,)
                )
            self.refresh_licenses()
            QMessageBox.information(self, "Success", "License unbanned successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error unbanning license: {str(e)}")
    
    def deactivate_license(self, license_key):
        """Deactivate a license key."""
        try:
            with DBConnection() as cursor:
                cursor.execute(
                    "UPDATE licenses SET status = 'inactive' WHERE license_key = %s",
                    (license_key,)
                )
            self.refresh_licenses()
            QMessageBox.information(self, "Success", "License deactivated successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error deactivating license: {str(e)}")
    
    def activate_license(self, license_key):
        """Activate a license key."""
        try:
            with DBConnection() as cursor:
                cursor.execute(
                    "UPDATE licenses SET status = 'active' WHERE license_key = %s",
                    (license_key,)
                )
            self.refresh_licenses()
            QMessageBox.information(self, "Success", "License activated successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error activating license: {str(e)}")
    
    def view_license_details(self, license_key):
        """View detailed information about a license key."""
        try:
            with DBConnection() as cursor:
                # Get license details
                cursor.execute(
                    "SELECT * FROM licenses WHERE license_key = %s",
                    (license_key,)
                )
                license_data = cursor.fetchone()
                
                if not license_data:
                    QMessageBox.warning(self, "Not Found", "License key not found")
                    return
                
                # Get activations for this license
                cursor.execute(
                    """
                    SELECT a.*, h.status as hw_status 
                    FROM activations a
                    JOIN hardware_ids h ON a.hardware_id = h.hardware_id
                    WHERE a.license_key = %s
                    """,
                    (license_key,)
                )
                activations = cursor.fetchall()
                
                # Get login attempts for this license
                cursor.execute(
                    """
                    SELECT * FROM login_attempts 
                    WHERE license_key = %s 
                    ORDER BY timestamp DESC 
                    LIMIT 10
                    """,
                    (license_key,)
                )
                attempts = cursor.fetchall()
                
                # Format data for display
                details = f"License Key: {license_data['license_key']}\n"
                details += f"Status: {license_data['status'].capitalize()}\n"
                details += f"Created: {license_data['creation_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                
                if license_data['expiration_date']:
                    details += f"Expires: {license_data['expiration_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                else:
                    details += "Expires: Never\n"
                
                details += f"\nActivations ({len(activations)}):\n"
                for activation in activations:
                    details += f"- Hardware: {activation['hardware_id']} "
                    details += f"(Status: {activation['hw_status']})\n"
                    details += f"  Activated: {activation['activation_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                    details += f"  Last Seen: {activation['last_verification'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                    details += f"  Legitimate: {'Yes' if activation['is_legitimate'] else 'No'}\n"
                
                details += f"\nRecent Login Attempts ({len(attempts)}):\n"
                for attempt in attempts:
                    details += f"- {attempt['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}: "
                    details += f"{'Success' if attempt['success'] else 'Failed'}\n"
                    details += f"  Hardware: {attempt['hardware_id']}\n"
                    if attempt['ip_address']:
                        details += f"  IP: {attempt['ip_address']}\n"
                
                details += f"\nNotes: {license_data['notes'] or 'N/A'}"
                
                # Display details in a message box
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle(f"License Details: {license_key}")
                msg_box.setText(details)
                msg_box.setStandardButtons(QMessageBox.Ok)
                msg_box.setDefaultButton(QMessageBox.Ok)
                msg_box.exec_()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error viewing license details: {str(e)}")
    
    def ban_hardware(self, hardware_id):
        """Ban a hardware ID."""
        # FIX: Use QInputDialog instead of QMessageBox.getText
        reason, ok = QInputDialog.getText(
            self, 
            "Ban Hardware ID", 
            "Enter reason for banning this hardware ID:",
            QLineEdit.Normal
        )
        
        if ok:
            try:
                with DBConnection() as cursor:
                    cursor.execute(
                        "UPDATE hardware_ids SET status = 'banned', ban_reason = %s WHERE hardware_id = %s",
                        (reason, hardware_id)
                    )
                self.refresh_hardware()
                QMessageBox.information(self, "Success", "Hardware ID banned successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error banning hardware ID: {str(e)}")
    
    def unban_hardware(self, hardware_id):
        """Unban a hardware ID."""
        try:
            with DBConnection() as cursor:
                cursor.execute(
                    "UPDATE hardware_ids SET status = 'active', ban_reason = NULL WHERE hardware_id = %s",
                    (hardware_id,)
                )
            self.refresh_hardware()
            QMessageBox.information(self, "Success", "Hardware ID unbanned successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error unbanning hardware ID: {str(e)}")
    
    def view_hardware_details(self, hardware_id):
        """View detailed information about a hardware ID."""
        try:
            with DBConnection() as cursor:
                # Get hardware details
                cursor.execute(
                    "SELECT * FROM hardware_ids WHERE hardware_id = %s",
                    (hardware_id,)
                )
                hw_data = cursor.fetchone()
                
                if not hw_data:
                    QMessageBox.warning(self, "Not Found", "Hardware ID not found")
                    return
                
                # Get activations for this hardware
                cursor.execute(
                    """
                    SELECT a.*, l.status as license_status 
                    FROM activations a
                    JOIN licenses l ON a.license_key = l.license_key
                    WHERE a.hardware_id = %s
                    """,
                    (hardware_id,)
                )
                activations = cursor.fetchall()
                
                # Get login attempts for this hardware
                cursor.execute(
                    """
                    SELECT * FROM login_attempts 
                    WHERE hardware_id = %s 
                    ORDER BY timestamp DESC 
                    LIMIT 10
                    """,
                    (hardware_id,)
                )
                attempts = cursor.fetchall()
                
                # Format data for display
                details = f"Hardware ID: {hw_data['hardware_id']}\n"
                details += f"Status: {hw_data['status'].capitalize()}\n"
                details += f"First Seen: {hw_data['first_seen'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                
                if hw_data['ban_reason']:
                    details += f"Ban Reason: {hw_data['ban_reason']}\n"
                
                details += f"\nActivations ({len(activations)}):\n"
                for activation in activations:
                    details += f"- License: {activation['license_key']} "
                    details += f"(Status: {activation['license_status']})\n"
                    details += f"  Activated: {activation['activation_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                    details += f"  Last Seen: {activation['last_verification'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                    details += f"  Legitimate: {'Yes' if activation['is_legitimate'] else 'No'}\n"
                
                details += f"\nRecent Login Attempts ({len(attempts)}):\n"
                for attempt in attempts:
                    details += f"- {attempt['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}: "
                    details += f"{'Success' if attempt['success'] else 'Failed'}\n"
                    details += f"  License: {attempt['license_key']}\n"
                    if attempt['ip_address']:
                        details += f"  IP: {attempt['ip_address']}\n"
                
                # Display details in a message box
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle(f"Hardware Details: {hardware_id[:8]}...")
                msg_box.setText(details)
                msg_box.setStandardButtons(QMessageBox.Ok)
                msg_box.setDefaultButton(QMessageBox.Ok)
                msg_box.exec_()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error viewing hardware details: {str(e)}")
    
    def delete_activation(self, license_key, hardware_id):
        """Delete an activation record."""
        reply = QMessageBox.question(
            self, 
            "Confirm Deletion", 
            f"Are you sure you want to delete the activation for:\nLicense: {license_key}\nHardware: {hardware_id}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                with DBConnection() as cursor:
                    cursor.execute(
                        "DELETE FROM activations WHERE license_key = %s AND hardware_id = %s",
                        (license_key, hardware_id)
                    )
                self.refresh_activations()
                QMessageBox.information(self, "Success", "Activation deleted successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error deleting activation: {str(e)}")
    
    def toggle_legitimacy(self, license_key, hardware_id, is_legitimate):
        """Toggle the legitimacy of an activation."""
        try:
            with DBConnection() as cursor:
                cursor.execute(
                    """UPDATE activations 
                       SET is_legitimate = %s 
                       WHERE license_key = %s AND hardware_id = %s""",
                    (is_legitimate, license_key, hardware_id)
                )
            self.refresh_activations()
            status = "legitimate" if is_legitimate else "illegitimate"
            QMessageBox.information(self, "Success", f"Activation marked as {status}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error updating activation: {str(e)}")

def main():
    app = QApplication(sys.argv)
    
    # Show login dialog first
    login_dialog = LoginDialog()
    if login_dialog.exec_() != QDialog.Accepted:
        return
    
    # Initialize database if needed
    try:
        from initialize_database import initialize_database
        initialize_database()
    except Exception as e:
        QMessageBox.warning(None, "Database Initialization", f"Error initializing database: {str(e)}")
    
    # Show admin panel
    admin_panel = AdminPanel()
    admin_panel.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()