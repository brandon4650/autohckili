import mysql.connector
import os
import sys

def initialize_database():
    """Set up the initial database schema"""
    conn = mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="ascent",
        port=3306
    )
    cursor = conn.cursor()
    
    # Create database if it doesn't exist
    cursor.execute("CREATE DATABASE IF NOT EXISTS auto_hekili_licenses")
    cursor.execute("USE auto_hekili_licenses")
    
    # Create licenses table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INT AUTO_INCREMENT PRIMARY KEY,
        license_key VARCHAR(50) UNIQUE NOT NULL,
        status ENUM('active', 'expired', 'banned', 'inactive') NOT NULL DEFAULT 'active',
        creation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expiration_date DATETIME NULL,
        notes TEXT NULL
    )
    """)
    
    # Create hardware_ids table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hardware_ids (
        id INT AUTO_INCREMENT PRIMARY KEY,
        hardware_id VARCHAR(50) UNIQUE NOT NULL,
        status ENUM('active', 'banned') NOT NULL DEFAULT 'active',
        first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ban_reason TEXT NULL
    )
    """)
    
    # Create activations table (linking licenses to hardware)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        license_key VARCHAR(50) NOT NULL,
        hardware_id VARCHAR(50) NOT NULL,
        activation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_verification DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        is_legitimate BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(license_key, hardware_id),
        FOREIGN KEY (license_key) REFERENCES licenses(license_key) ON DELETE CASCADE,
        FOREIGN KEY (hardware_id) REFERENCES hardware_ids(hardware_id) ON DELETE CASCADE
    )
    """)
    
    # Create login attempts table for security monitoring
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        license_key VARCHAR(50) NOT NULL,
        hardware_id VARCHAR(50) NOT NULL,
        timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        success BOOLEAN NOT NULL DEFAULT FALSE,
        ip_address VARCHAR(45) NULL,
        client_info TEXT NULL
    )
    """)
    
    # Create admin access table with a single admin user
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        last_login DATETIME NULL
    )
    """)
    
    # Check if admin user exists, if not create one
    cursor.execute("SELECT COUNT(*) FROM admin_users")
    if cursor.fetchone()[0] == 0:
        import hashlib
        admin_password = "admin123"  # Default password, should be changed immediately
        password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)",
            ("admin", password_hash)
        )
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

if __name__ == "__main__":
    initialize_database()