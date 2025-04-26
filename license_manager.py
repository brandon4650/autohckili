import mysql.connector
import os
import sys
import time
import signal
import traceback
import logging

class DatabaseTimeoutError(Exception):
    """Custom exception for database timeout"""
    pass

def timeout_handler(signum, frame):
    """Handle timeout signal"""
    raise DatabaseTimeoutError("Database operation timed out after 15 seconds")

def initialize_database():
    """Set up the initial database schema with timeout handling"""
    print("Starting database initialization...")
    logging.info("Starting database initialization...")
    
    # Set timeout for database operations (15 seconds)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(15)  
    
    conn = None
    cursor = None
    
    try:
        print("Connecting to MySQL server...")
        logging.info("Connecting to MySQL server...")
        
        # Step 1: Connect to MySQL without database
        conn = mysql.connector.connect(
            host="127.0.0.1",
            user="root",
            password="ascent",
            port=3306,
            connection_timeout=10
        )
        
        print("MySQL server connection successful")
        logging.info("MySQL server connection successful")
        
        cursor = conn.cursor()
        
        # Step 2: Create database if it doesn't exist
        print("Creating database if needed...")
        logging.info("Creating database if needed...")
        cursor.execute("CREATE DATABASE IF NOT EXISTS auto_hekili_licenses")
        
        # Close initial connection
        cursor.close()
        conn.close()
        
        # Step 3: Reconnect with database specified
        print("Connecting to auto_hekili_licenses database...")
        logging.info("Connecting to auto_hekili_licenses database...")
        conn = mysql.connector.connect(
            host="127.0.0.1",
            user="root",
            password="ascent",
            port=3306,
            database="auto_hekili_licenses",
            connection_timeout=10
        )
        cursor = conn.cursor()
        
        # Step 4: Create licenses table
        print("Creating licenses table...")
        logging.info("Creating licenses table...")
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
        
        # Step 5: Create hardware_ids table
        print("Creating hardware_ids table...")
        logging.info("Creating hardware_ids table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hardware_ids (
            id INT AUTO_INCREMENT PRIMARY KEY,
            hardware_id VARCHAR(50) UNIQUE NOT NULL,
            status ENUM('active', 'banned') NOT NULL DEFAULT 'active',
            first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ban_reason TEXT NULL
        )
        """)
        
        # Step 6: Create activations table
        print("Creating activations table...")
        logging.info("Creating activations table...")
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
        
        # Step 7: Create login attempts table
        print("Creating login_attempts table...")
        logging.info("Creating login_attempts table...")
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
        
        # Step 8: Create admin users table
        print("Creating admin_users table...")
        logging.info("Creating admin_users table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_login DATETIME NULL
        )
        """)
        
        # Step 9: Check for admin user
        print("Checking for admin user...")
        logging.info("Checking for admin user...")
        cursor.execute("SELECT COUNT(*) FROM admin_users")
        if cursor.fetchone()[0] == 0:
            print("Creating default admin user...")
            logging.info("Creating default admin user...")
            import hashlib
            admin_password = "admin123"
            password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
            cursor.execute(
                "INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)",
                ("admin", password_hash)
            )
        
        conn.commit()
        
        # Step 10: Check for license keys
        print("Checking for license keys...")
        logging.info("Checking for license keys...")
        cursor.execute("SELECT COUNT(*) FROM licenses")
        license_count = cursor.fetchone()[0]
        
        # If no license keys exist, add the pre-generated ones
        if license_count == 0:
            print("Adding pre-generated license keys...")
            logging.info("Adding pre-generated license keys...")
            
            # Use license keys from your pre-generated list [[1]](https://poe.com/citation?message_id=381808706688&citation=1)
            valid_keys = [
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
            
            for key in valid_keys:
                try:
                    cursor.execute(
                        "INSERT INTO licenses (license_key) VALUES (%s)",
                        (key,)
                    )
                except mysql.connector.Error as e:
                    # Just log errors but continue with other keys
                    print(f"Error adding license key {key}: {e}")
                    logging.warning(f"Error adding license key {key}: {e}")
            
            conn.commit()
        
        print("Database initialization completed successfully!")
        logging.info("Database initialization completed successfully!")
        
    except DatabaseTimeoutError as timeout_err:
        print(f"Database operation timed out: {timeout_err}")
        logging.error(f"Database operation timed out: {timeout_err}")
        if conn:
            conn.rollback()
        raise
    except mysql.connector.Error as db_err:
        print(f"MySQL error: {db_err}")
        logging.error(f"MySQL error: {db_err}")
        logging.error(traceback.format_exc())
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        logging.error(f"Unexpected error: {e}")
        logging.error(traceback.format_exc())
        if conn:
            conn.rollback()
        raise
    finally:
        # Cancel the timeout alarm
        signal.alarm(0)
        
        # Close database connections
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    # Configure logging when run directly
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        initialize_database()
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)