import os
import json
import time
import cv2
import numpy as np
import pyautogui
import pydirectinput
from PIL import Image, ImageGrab
import imagehash
import keyboard
import threading
import re
import sys
from os import listdir
from os.path import isfile, join
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QPushButton, QComboBox, QLineEdit, 
                            QScrollArea, QFormLayout, QGridLayout, QGroupBox, QTextEdit,
                            QCheckBox, QSlider, QSplitter, QFrame, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QPixmap, QImage, QPalette, QColor, QFont, QIcon

# Constants
CONFIG_PATH = "config\\config.json"
IMG_DIR = "img"
SIMC_NOTES_DIR = "config\\Notes"
DEBUG_DIR = "debug_captures"

# Function to convert PIL Image to QImage
def pil_to_qimage(pil_image):
    """Convert PIL Image to QImage."""
    if pil_image.mode == "RGB":
        r, g, b = pil_image.split()
        pil_image = Image.merge("RGB", (b, g, r))
        data = pil_image.convert("RGB").tobytes("raw", "RGB")
        qimage = QImage(data, pil_image.size[0], pil_image.size[1], pil_image.size[0] * 3, QImage.Format_RGB888)
        return qimage
    elif pil_image.mode == "RGBA":
        data = pil_image.convert("RGBA").tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.size[0], pil_image.size[1], pil_image.size[0] * 4, QImage.Format_RGBA8888)
        return qimage
    else:
        pil_image = pil_image.convert("RGBA")
        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.size[0], pil_image.size[1], pil_image.size[0] * 4, QImage.Format_RGBA8888)
        return qimage

class CaptureThread(QThread):
    """Thread for screen capture and spell recognition."""
    update_signal = pyqtSignal(str)
    spell_signal = pyqtSignal(str)
    image_signal = pyqtSignal(QImage)
    
    def __init__(self, box_position, spell_info, threshold=15):
        super().__init__()
        self.box_position = box_position
        self.spell_info = spell_info
        self.threshold = threshold
        self.running = False
        self.active = True
        self.stop_requested = False
        
        # Create debug directory
        os.makedirs(DEBUG_DIR, exist_ok=True)
        
        # Special handling for problematic spells
        self.problem_spells = ["storm_elemental", "ascendance"]
        self.problem_spell_info = {s: info for s, info in spell_info.items() 
                                 if any(p.lower() in s.lower() for p in self.problem_spells)}
        
        # Print debug info for problem spells
        for spell_name, info in self.problem_spell_info.items():
            self.update_signal.emit(f"Special handling enabled for: {spell_name}")
            self.update_signal.emit(f"  - Icon path: {info['icon_path']}")
            self.update_signal.emit(f"  - Keybind: {info['key']}")
            if os.path.exists(info["icon_path"]):
                img = Image.open(info["icon_path"])
                img.save(os.path.join(DEBUG_DIR, f"reference_{spell_name}.png"))
        
        # Prepare spell hashes
        self.spell_hashes = {}
        for spell_name, info in spell_info.items():
            if os.path.exists(info["icon_path"]):
                try:
                    img = Image.open(info["icon_path"])
                    self.spell_hashes[spell_name] = imagehash.phash(img)
                except Exception as e:
                    self.update_signal.emit(f"Error loading image for {spell_name}: {e}")
    
    def run(self):
        """Main thread loop for capture and comparison."""
        self.running = True
        capture_count = 0
        last_spell = None
        
        while not self.stop_requested:
            # Check for F3 key to toggle automation
            if keyboard.is_pressed('f3'):
                self.active = not self.active
                status = "activated" if self.active else "paused"
                self.update_signal.emit(f"Automation {status}")
                time.sleep(0.3)  # Debounce
            
            if self.active:
                try:
                    # Capture the screen region
                    left, top, width, height = self.box_position
                    region = (left, top, left + width, top + height)
                    screenshot = ImageGrab.grab(bbox=region)
                    
                    # Update UI with current screenshot (every 10 frames)
                    if capture_count % 10 == 0:
                        qt_img = pil_to_qimage(screenshot)
                        self.image_signal.emit(qt_img)
                    
                    # Save occasional screenshots for debugging
                    if capture_count % 200 == 0:
                        screenshot.save(os.path.join(DEBUG_DIR, f"capture_{capture_count}.png"))
                    
                    # First try template matching for problematic spells
                    problem_spell_matched = False
                    for spell_name, info in self.problem_spell_info.items():
                        # Convert to CV2 format
                        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                        template = cv2.imread(info["icon_path"])
                        
                        if template is not None:
                            # Use template matching with multiple scales for better accuracy
                            max_val_overall = 0
                            for scale in [1.0, 0.95, 0.9]:
                                scaled_template = cv2.resize(template, (0, 0), fx=scale, fy=scale)
                                if scaled_template.shape[0] <= screenshot_cv.shape[0] and scaled_template.shape[1] <= screenshot_cv.shape[1]:
                                    result = cv2.matchTemplate(screenshot_cv, scaled_template, cv2.TM_CCOEFF_NORMED)
                                    _, max_val, _, _ = cv2.minMaxLoc(result)
                                    max_val_overall = max(max_val_overall, max_val)
                            
                            # If strong match found (threshold can be adjusted)
                            if max_val_overall >= 0.7:
                                # Save this detection
                                if spell_name != last_spell:
                                    self.update_signal.emit(f"Template matching found: {spell_name} (confidence: {max_val_overall:.2f})")
                                    screenshot.save(os.path.join(DEBUG_DIR, f"detected_{spell_name}_{capture_count}.png"))
                                    last_spell = spell_name
                                    self.spell_signal.emit(spell_name)
                                
                                # Press the key
                                key = info["key"]
                                if key:
                                    self.press_key_combination(key)
                                    time.sleep(0.1)  # Small delay to prevent key spamming
                                
                                problem_spell_matched = True
                                break
                    
                    # If no problem spell was found, use the regular phash method
                    if not problem_spell_matched:
                        # Compare with spell icons
                        current_hash = imagehash.phash(screenshot)
                        best_match = None
                        min_diff = float('inf')
                        
                        for spell_name, phash in self.spell_hashes.items():
                            diff = phash - current_hash
                            # Use lower threshold for problem spells
                            if any(p.lower() in spell_name.lower() for p in self.problem_spells):
                                if diff < min_diff and diff < 12:  # Lower threshold for problem spells
                                    min_diff = diff
                                    best_match = spell_name
                            elif diff < min_diff:
                                min_diff = diff
                                best_match = spell_name
                        
                        # If a match is found and it's close enough
                        is_problem_spell = best_match and any(p.lower() in best_match.lower() for p in self.problem_spells)
                        threshold = 12 if is_problem_spell else self.threshold
                        
                        if best_match and min_diff < threshold:
                            # Only log when spell changes
                            if best_match != last_spell:
                                self.update_signal.emit(f"Hash matching found: {best_match} (diff: {min_diff})")
                                last_spell = best_match
                                self.spell_signal.emit(best_match)
                            
                            key = self.spell_info[best_match]["key"]
                            if key:
                                self.press_key_combination(key)
                                time.sleep(0.1)  # Small delay to prevent key spamming
                    
                    capture_count += 1
                    time.sleep(0.05)  # Small delay between captures
                
                except Exception as e:
                    self.update_signal.emit(f"Error in capture and compare: {e}")
                    time.sleep(1)
            else:
                time.sleep(0.1)
        
        self.running = False
    
    def stop(self):
        """Stop the thread."""
        self.stop_requested = True
        self.wait()
    
    def press_key_combination(self, key_combo):
        """Press a key combination which may include modifier keys."""
        if '+' in key_combo:
            parts = key_combo.lower().split('+')
            modifier = parts[0].strip()
            key = parts[1].strip()
            
            if modifier == 'alt':
                keyboard.press('alt')
                time.sleep(0.05)  # Small delay to ensure modifier is registered
                pydirectinput.press(key)
                time.sleep(0.05)
                keyboard.release('alt')
            elif modifier == 'ctrl':
                keyboard.press('ctrl')
                time.sleep(0.05)
                pydirectinput.press(key)
                time.sleep(0.05)
                keyboard.release('ctrl')
            elif modifier == 'shift':
                keyboard.press('shift')
                time.sleep(0.05)
                pydirectinput.press(key)
                time.sleep(0.05)
                keyboard.release('shift')
        else:
            # For regular keys without modifiers
            pydirectinput.press(key_combo)


class SpellTestThread(QThread):
    """Thread for testing spell recognition."""
    update_signal = pyqtSignal(str)
    image_signal = pyqtSignal(QImage)
    
    def __init__(self, box_position, spell_info, spell_to_test, threshold=15):
        super().__init__()
        self.box_position = box_position
        self.spell_info = spell_info
        self.spell_to_test = spell_to_test
        self.threshold = threshold
    
    def run(self):
        """Test recognition for a specific spell."""
        os.makedirs(DEBUG_DIR, exist_ok=True)
        
        # Find the spell
        test_spell = None
        for spell_name, info in self.spell_info.items():
            if self.spell_to_test.lower() in spell_name.lower():
                test_spell = (spell_name, info)
                break
        
        if not test_spell:
            self.update_signal.emit(f"Error: {self.spell_to_test} not found in current class/spec")
            return
        
        spell_name, info = test_spell
        self.update_signal.emit(f"Testing recognition for: {spell_name}")
        self.update_signal.emit(f"Icon path: {info['icon_path']}")
        
        if not os.path.exists(info["icon_path"]):
            self.update_signal.emit(f"Error: Icon file not found: {info['icon_path']}")
            return
        
        # Capture the screen region
        left, top, width, height = self.box_position
        region = (left, top, left + width, top + height)
        screenshot = ImageGrab.grab(bbox=region)
        
        # Send screenshot to UI
        qt_img = pil_to_qimage(screenshot)
        self.image_signal.emit(qt_img)
        
        # Save for debugging
        screenshot.save(os.path.join(DEBUG_DIR, f"test_{spell_name}.png"))
        
        # Test recognition with perceptual hash
        ref_img = Image.open(info["icon_path"])
        ref_hash = imagehash.phash(ref_img)
        current_hash = imagehash.phash(screenshot)
        hash_diff = ref_hash - current_hash
        
        self.update_signal.emit(f"Hash comparison: diff = {hash_diff}")
        self.update_signal.emit(f"Current threshold: {self.threshold}")
        result = "MATCH" if hash_diff < self.threshold else "NO MATCH"
        self.update_signal.emit(f"Result: {result}")
        
        # Test with template matching
        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        template = cv2.imread(info["icon_path"])
        if template is not None:
            # Try different scales for template matching
            for scale in [1.0, 0.95, 0.9, 0.85]:
                scaled_template = cv2.resize(template, (0, 0), fx=scale, fy=scale)
                
                # Skip if template is larger than image
                if scaled_template.shape[0] > screenshot_cv.shape[0] or scaled_template.shape[1] > screenshot_cv.shape[1]:
                    self.update_signal.emit(f"Template matching (scale {scale}): skipped - template too large")
                    continue
                
                result = cv2.matchTemplate(screenshot_cv, scaled_template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                self.update_signal.emit(f"Template matching (scale {scale}): confidence = {max_val:.4f}")
                tm_result = "MATCH" if max_val >= 0.7 else "NO MATCH"
                self.update_signal.emit(f"Template result: {tm_result}")


class AutoHekiliGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUTO_Hekili")
        self.setGeometry(100, 100, 900, 700)
        
        # App state
        self.config = self.load_config()
        self.box_position = None
        self.spell_info = {}
        self.capture_thread = None
        self.current_spell = None
        
        # Set dark theme
        self.set_dark_theme()
        
        # Set up the UI
        self.init_ui()
        
        # Load existing configuration if available
        self.load_existing_config()
    
    def init_ui(self):
        """Initialize the UI."""
        # Create main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.setup_tab = QWidget()
        self.config_tab = QWidget()
        self.debug_tab = QWidget()
        self.runner_tab = QWidget()
        
        self.tab_widget.addTab(self.setup_tab, "Setup")
        self.tab_widget.addTab(self.config_tab, "Keybindings")
        self.tab_widget.addTab(self.debug_tab, "Debug")
        self.tab_widget.addTab(self.runner_tab, "Runner")
        
        # Initialize tab UIs
        self.init_setup_tab()
        self.init_config_tab()
        self.init_debug_tab()
        self.init_runner_tab()
        
        # Set the main widget
        self.setCentralWidget(main_widget)
        
        # Status bar
        self.statusBar().showMessage("Ready")

    def set_wow_theme(self):
        """Set World of Warcraft theme for the application."""
        # WoW themed colors
        wow_dark_blue = QColor(15, 25, 41)      # Dark background like WoW UI panels
        wow_medium_blue = QColor(24, 41, 66)    # Medium blue for alternate backgrounds
        wow_light_blue = QColor(52, 86, 127)    # Light blue for highlights
        wow_gold = QColor(218, 165, 32)         # WoW gold for borders and important elements
        wow_bright_gold = QColor(255, 209, 0)   # Brighter gold for text
        
        # Create palette and apply colors
        wow_palette = QPalette()
        wow_palette.setColor(QPalette.Window, wow_dark_blue)
        wow_palette.setColor(QPalette.WindowText, wow_bright_gold)
        wow_palette.setColor(QPalette.Base, wow_medium_blue)
        wow_palette.setColor(QPalette.AlternateBase, wow_dark_blue)
        wow_palette.setColor(QPalette.ToolTipBase, wow_dark_blue)
        wow_palette.setColor(QPalette.ToolTipText, wow_bright_gold)
        wow_palette.setColor(QPalette.Text, wow_bright_gold)
        wow_palette.setColor(QPalette.Button, wow_light_blue)
        wow_palette.setColor(QPalette.ButtonText, Qt.white)
        wow_palette.setColor(QPalette.BrightText, Qt.white)
        wow_palette.setColor(QPalette.Link, wow_gold)
        wow_palette.setColor(QPalette.Highlight, wow_gold)
        wow_palette.setColor(QPalette.HighlightedText, Qt.black)
        
        self.setPalette(wow_palette)
        
        # Apply WoW-style stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0F1929; /* Dark blue background */
            }
            
            QWidget {
                background-color: #0F1929;
                color: #FFD100;
            }
            
            QGroupBox {
                border: 1px solid #D4AF37; /* Gold border */
                border-radius: 5px;
                margin-top: 15px;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 10px;
                color: #FFD100; /* Gold text */
                background-color: #0F1929; /* Match the dark background */
            }
            
            QPushButton {
                background-color: #344E7F; /* WoW blue button */
                border: 1px solid #D4AF37; /* Gold border */
                border-radius: 3px;
                padding: 8px;
                font-weight: bold;
                min-height: 24px;
                color: white;
            }
            
            QPushButton:hover {
                background-color: #4A6EA5; /* Lighter blue when hovering */
            }
            
            QPushButton:pressed {
                background-color: #263A5E; /* Darker blue when pressed */
            }
            
            QTabWidget::pane {
                border: 1px solid #D4AF37; /* Gold border */
                border-radius: 3px;
                top: -1px;
            }
            
            QTabBar::tab {
                background-color: #19294A; /* Darker blue for tabs */
                color: #FFD100; /* Gold text */
                border: 1px solid #D4AF37; /* Gold border */
                border-bottom-color: #19294A;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                min-width: 80px;
                padding: 8px 12px;
                font-weight: bold;
                margin-right: 4px;
            }
            
            QTabBar::tab:selected {
                background-color: #344E7F; /* Brighter blue for selected tab */
                border-bottom-color: #344E7F;
            }
            
            QTabBar::tab:!selected {
                margin-top: 2px;
            }
            
            QLineEdit, QComboBox {
                background-color: #19294A; /* Darker blue for input fields */
                border: 1px solid #344E7F; /* Blue border */
                border-radius: 3px;
                padding: 5px;
                color: #FFD100; /* Gold text */
                font-weight: bold;
                selection-background-color: #4A6EA5;
                min-height: 24px;
            }
            
            QTextEdit {
                background-color: #19294A; /* Darker blue */
                border: 1px solid #344E7F; /* Blue border */
                border-radius: 3px;
                padding: 5px;
                color: #CCCCCC; /* Light gray text for readability */
                selection-background-color: #4A6EA5;
            }
            
            QLabel {
                color: #FFD100; /* Gold text */
                font-weight: bold;
                padding: 2px;
            }
            
            QScrollArea {
                border: 1px solid #344E7F;
                border-radius: 3px;
            }
            
            QScrollBar:vertical {
                border: 1px solid #344E7F;
                background: #19294A;
                width: 15px;
                margin: 15px 0 15px 0;
            }
            
            QScrollBar::handle:vertical {
                background: #344E7F; /* Blue handle */
                min-height: 20px;
                border-radius: 3px;
            }
            
            QScrollBar::add-line:vertical {
                border: 1px solid #344E7F;
                background: #344E7F;
                height: 15px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }
            
            QScrollBar::sub-line:vertical {
                border: 1px solid #344E7F;
                background: #344E7F;
                height: 15px;
                subcontrol-position: top;
                subcontrol-origin: margin;
            }
            
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                width: 8px;
                height: 8px;
                background: #FFD100; /* Gold arrows */
            }
            
            QSlider::groove:horizontal {
                border: 1px solid #344E7F;
                background: #19294A;
                height: 8px;
                border-radius: 4px;
            }
            
            QSlider::handle:horizontal {
                background: #D4AF37; /* Gold handle */
                border: 1px solid #D4AF37;
                width: 18px;
                margin: -2px 0;
                border-radius: 5px;
            }
            
            QStatusBar {
                background-color: #19294A;
                color: #FFD100;
                font-weight: bold;
                border-top: 1px solid #D4AF37;
            }
        """)
    
    def init_setup_tab(self):
        """Initialize the setup tab with WoW-style interface."""
        layout = QVBoxLayout(self.setup_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Introduction
        intro_box = QGroupBox("Welcome to AUTO_Hekili")
        intro_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        intro_layout = QVBoxLayout()
        
        intro_text = QLabel(
            "<p style='font-size: 13px; line-height: 150%;'>"
            "This application automates spell casting based on <b>Hekili addon</b> recommendations in World of Warcraft.<br><br>"
            "<span style='color: #FF6060; font-weight: bold;'>WARNING:</span> Using automation tools may violate World of Warcraft's Terms of Service.<br>"
            "Use at your own risk!</p>"
        )
        intro_text.setTextFormat(Qt.RichText)
        intro_text.setWordWrap(True)
        intro_layout.addWidget(intro_text)
        
        # Add requirements info
        requirements = QLabel(
            "<p style='font-size: 12px;'><b>Requirements:</b><br>"
            "• <a href='https://www.curseforge.com/wow/addons/hekili'>Hekili Addon</a> installed in WoW<br>"
            "• Hekili configured to show a single icon recommendation<br>"
            "• WoW running in Windowed or Windowed (Fullscreen) mode</p>"
        )
        requirements.setTextFormat(Qt.RichText)
        requirements.setWordWrap(True)
        requirements.setOpenExternalLinks(True)
        requirements.setStyleSheet("color: #BBBBBB;")
        intro_layout.addWidget(requirements)
        
        intro_box.setLayout(intro_layout)
        layout.addWidget(intro_box)
        
        # Class and spec selection with WoW styling
        class_box = QGroupBox("Step 1: Select Class & Specialization")
        class_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        class_layout = QVBoxLayout()
        
        class_desc = QLabel("Select your character's class and specialization from the dropdown below.")
        class_desc.setStyleSheet("color: #BBBBBB;")
        class_layout.addWidget(class_desc)
        
        class_combo_layout = QHBoxLayout()
        class_combo_layout.addWidget(QLabel("Class/Spec:"))
        
        self.class_combo = QComboBox()
        self.class_combo.addItems(self.get_available_classes_specs())
        self.class_combo.setStyleSheet("""
            QComboBox {
                background-color: #19294A;
                border: 1px solid #344E7F;
                border-radius: 3px;
                padding: 5px;
                color: #FFD100;
                font-weight: bold;
                selection-background-color: #4A6EA5;
                min-width: 200px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox::down-arrow {
                image: url(dropdown_arrow.png);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #19294A;
                border: 1px solid #344E7F;
                selection-background-color: #4A6EA5;
                color: #FFD100;
            }
        """)
        
        if "Class" in self.config and self.config["Class"]:
            idx = self.class_combo.findText(self.config["Class"])
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)
        
        class_combo_layout.addWidget(self.class_combo)
        class_combo_layout.addStretch()
        class_layout.addLayout(class_combo_layout)
        
        class_box.setLayout(class_layout)
        layout.addWidget(class_box)
        
        # Screen region selection with WoW styling
        region_box = QGroupBox("Step 2: Select Hekili Spellbox Region")
        region_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        region_layout = QVBoxLayout()
        
        region_desc = QLabel(
            "Select the screen region where Hekili displays its primary spell recommendation icon.<br>"
            "<b>Tip:</b> Make sure to capture only the primary icon, not the entire action bar."
        )
        region_desc.setTextFormat(Qt.RichText)
        region_desc.setStyleSheet("color: #BBBBBB;")
        region_desc.setWordWrap(True)
        region_layout.addWidget(region_desc)
        
        region_btn_layout = QHBoxLayout()
        region_btn_layout.addWidget(QLabel("Selected Region:"))
        
        self.region_label = QLabel("Not selected")
        self.region_label.setStyleSheet("""
            background-color: #19294A;
            border: 1px solid #344E7F;
            border-radius: 3px;
            padding: 5px;
            color: #FFD100;
            min-width: 120px;
        """)
        region_btn_layout.addWidget(self.region_label)
        
        self.select_region_btn = QPushButton("Select Region")
        self.select_region_btn.setStyleSheet("""
            QPushButton {
                background-color: #344E7F;
                color: white;
                font-weight: bold;
                border: 1px solid #D4AF37;
                border-radius: 3px;
                padding: 8px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #4A6EA5;
            }
        """)
        self.select_region_btn.clicked.connect(self.select_region)
        region_btn_layout.addWidget(self.select_region_btn)
        region_btn_layout.addStretch()
        region_layout.addLayout(region_btn_layout)
        
        region_box.setLayout(region_layout)
        layout.addWidget(region_box)
        
        # Apply setup with WoW styling
        apply_box = QGroupBox("Step 3: Apply Setup")
        apply_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        apply_layout = QVBoxLayout()
        
        apply_desc = QLabel(
            "Once you've selected your class/spec and the Hekili icon region, click Apply Setup to proceed to keybindings."
        )
        apply_desc.setStyleSheet("color: #BBBBBB;")
        apply_desc.setWordWrap(True)
        apply_layout.addWidget(apply_desc)
        
        self.apply_btn = QPushButton("APPLY SETUP")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #1F6032;
                color: white;
                font-weight: bold;
                border: 2px solid #D4AF37;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2A8045;
            }
        """)
        self.apply_btn.clicked.connect(self.apply_setup)
        
        apply_layout.addWidget(self.apply_btn, alignment=Qt.AlignCenter)
        apply_box.setLayout(apply_layout)
        layout.addWidget(apply_box)
        
        # Add spacer
        layout.addStretch()
    
    def init_config_tab(self):
        """Initialize the keybindings tab with WoW-style interface."""
        layout = QVBoxLayout(self.config_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header with instructions
        header_box = QGroupBox("Keybinding Instructions")
        header_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        header_layout = QVBoxLayout()
        
        instructions = QLabel(
            "Configure keybindings for your spells. These must match your in-game keybindings.<br>"
            "• Leave empty or type 'skip' to ignore spells you don't want to cast<br>"
            "• For modifier keys, use format: <b>alt+key</b>, <b>ctrl+key</b>, <b>shift+key</b> (e.g., 'alt+1', 'ctrl+f')"
        )
        instructions.setTextFormat(Qt.RichText)
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #BBBBBB; padding: 5px;")
        header_layout.addWidget(instructions)
        header_box.setLayout(header_layout)
        layout.addWidget(header_box)
        
        # Create a scroll area with WoW styling
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #0F1929;
                border: 2px solid #344E7F;
                border-radius: 5px;
            }
        """)
        
        # Create the keybind widget
        self.keybind_widget = QWidget()
        self.keybind_widget.setStyleSheet("background-color: #0F1929;")
        
        # Use grid layout for better control
        self.keybind_layout = QGridLayout(self.keybind_widget)
        self.keybind_layout.setContentsMargins(5, 5, 5, 5)
        self.keybind_layout.setSpacing(0)
        
        # Add header row
        header_font = QFont()
        header_font.setBold(True)
        
        header_spell = QLabel("Spell Name")
        header_spell.setFont(header_font)
        header_spell.setStyleSheet("color: #FFD100; padding: 5px; border-bottom: 1px solid #344E7F;")
        self.keybind_layout.addWidget(header_spell, 0, 0)
        
        header_key = QLabel("Keybind")
        header_key.setFont(header_font)
        header_key.setStyleSheet("color: #FFD100; padding: 5px; border-bottom: 1px solid #344E7F;")
        header_key.setAlignment(Qt.AlignCenter)
        self.keybind_layout.addWidget(header_key, 0, 1)
        
        scroll.setWidget(self.keybind_widget)
        layout.addWidget(scroll)
        
        # Button container with WoW styling
        button_container = QWidget()
        button_container.setStyleSheet("background-color: transparent;")
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        # Save button with green background
        self.save_keybinds_btn = QPushButton("Save Keybindings")
        self.save_keybinds_btn.setStyleSheet("""
            QPushButton {
                background-color: #1F6032;
                color: white;
                font-weight: bold;
                border: 1px solid #D4AF37;
                border-radius: 3px;
                padding: 8px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2A8045;
            }
        """)
        self.save_keybinds_btn.clicked.connect(self.save_keybindings)
        button_layout.addWidget(self.save_keybinds_btn)
        
        # Reset button with red background
        self.reset_keybinds_btn = QPushButton("Reset All")
        self.reset_keybinds_btn.setStyleSheet("""
            QPushButton {
                background-color: #722424;
                color: white;
                font-weight: bold;
                border: 1px solid #D4AF37;
                border-radius: 3px;
                padding: 8px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #9B3232;
            }
        """)
        self.reset_keybinds_btn.clicked.connect(self.reset_keybindings)
        button_layout.addWidget(self.reset_keybinds_btn)
        
        layout.addWidget(button_container)
        
        # Add key hints at bottom
        hints_label = QLabel(
            "<b>Pro Tips:</b> For best results, use simple keys like 1-9 or F1-F12.<br>"
            "Avoid using modifiers for frequently cast spells."
        )
        hints_label.setTextFormat(Qt.RichText)
        hints_label.setStyleSheet("color: #BBBBBB; font-style: italic; margin-top: 10px;")
        layout.addWidget(hints_label)
    
    def init_debug_tab(self):
        """Initialize the debug tab with WoW-style interface."""
        layout = QVBoxLayout(self.debug_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Split the debug tab into two parts with WoW-style splitter
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #344E7F;
                border: 1px solid #D4AF37;
            }
        """)
        
        # Top part - testing controls
        top_widget = QWidget()
        top_widget.setStyleSheet("background-color: #0F1929;")
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Problem spell testing
        problem_box = QGroupBox("Test Recognition for Problematic Spells")
        problem_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        problem_layout = QVBoxLayout()
        
        # Instructions
        test_instructions = QLabel(
            "Test recognition for problematic spells that might need special handling.<br>"
            "<b>Step 1:</b> Make sure Hekili is showing the spell you want to test in-game.<br>"
            "<b>Step 2:</b> Click the test button for that spell to check if it's recognized properly."
        )
        test_instructions.setTextFormat(Qt.RichText)
        test_instructions.setWordWrap(True)
        test_instructions.setStyleSheet("color: #BBBBBB; padding: 5px;")
        problem_layout.addWidget(test_instructions)
        
        # Test buttons with spell icons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        # Storm Elemental button
        storm_btn_container = QWidget()
        storm_btn_layout = QVBoxLayout(storm_btn_container)
        storm_btn_layout.setContentsMargins(5, 5, 5, 5)
        
        self.test_storm_btn = QPushButton("Test Storm Elemental")
        self.test_storm_btn.setStyleSheet("""
            QPushButton {
                background-color: #344E7F;
                color: white;
                font-weight: bold;
                border: 1px solid #D4AF37;
                border-radius: 3px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #4A6EA5;
            }
        """)
        self.test_storm_btn.clicked.connect(lambda: self.test_spell_recognition("storm_elemental"))
        storm_btn_layout.addWidget(self.test_storm_btn)
        
        # Storm Elemental description
        storm_desc = QLabel("Tests if Storm Elemental icon is properly detected")
        storm_desc.setStyleSheet("color: #BBBBBB; font-style: italic; font-size: 11px;")
        storm_btn_layout.addWidget(storm_desc)
        
        btn_layout.addWidget(storm_btn_container)
        
        # Ascendance button
        asc_btn_container = QWidget()
        asc_btn_layout = QVBoxLayout(asc_btn_container)
        asc_btn_layout.setContentsMargins(5, 5, 5, 5)
        
        self.test_ascendance_btn = QPushButton("Test Ascendance")
        self.test_ascendance_btn.setStyleSheet("""
            QPushButton {
                background-color: #344E7F;
                color: white;
                font-weight: bold;
                border: 1px solid #D4AF37;
                border-radius: 3px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #4A6EA5;
            }
        """)
        self.test_ascendance_btn.clicked.connect(lambda: self.test_spell_recognition("ascendance"))
        asc_btn_layout.addWidget(self.test_ascendance_btn)
        
        # Ascendance description
        asc_desc = QLabel("Tests if Ascendance icon is properly detected")
        asc_desc.setStyleSheet("color: #BBBBBB; font-style: italic; font-size: 11px;")
        asc_btn_layout.addWidget(asc_desc)
        
        btn_layout.addWidget(asc_btn_container)
        problem_layout.addLayout(btn_layout)
        
        # Threshold adjustment with WoW styling
        threshold_box = QGroupBox("Recognition Settings")
        threshold_box.setStyleSheet("""
            QGroupBox {
                background-color: #0F1929;
                border: 1px solid #344E7F;
                border-radius: 5px;
                margin-top: 15px;
            }
        """)
        threshold_layout = QVBoxLayout()
        
        threshold_desc = QLabel("Adjust the threshold for spell recognition. Lower values make recognition more sensitive but may cause false positives.")
        threshold_desc.setWordWrap(True)
        threshold_desc.setStyleSheet("color: #BBBBBB; font-style: italic;")
        threshold_layout.addWidget(threshold_desc)
        
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Threshold:"))
        
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(5)
        self.threshold_slider.setMaximum(25)
        self.threshold_slider.setValue(15)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(5)
        self.threshold_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #19294A;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #D4AF37;
                border: 1px solid #D4AF37;
                width: 18px;
                margin: -2px 0;
                border-radius: 5px;
            }
        """)
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)
        slider_layout.addWidget(self.threshold_slider)
        
        self.threshold_label = QLabel("15")
        self.threshold_label.setStyleSheet("color: #FFD100; font-weight: bold; min-width: 30px;")
        slider_layout.addWidget(self.threshold_label)
        
        threshold_layout.addLayout(slider_layout)
        threshold_box.setLayout(threshold_layout)
        problem_layout.addWidget(threshold_box)
        
        # Capture preview with WoW styling
        capture_box = QGroupBox("Current Capture")
        capture_box.setStyleSheet("""
            QGroupBox {
                background-color: #0F1929;
                border: 1px solid #344E7F;
                border-radius: 5px;
                margin-top: 15px;
            }
        """)
        capture_layout = QVBoxLayout()
        
        preview_container = QWidget()
        preview_layout = QHBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(100, 100)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            border: 2px solid #344E7F;
            background-color: #0A101E;
        """)
        preview_layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)
        
        self.refresh_capture_btn = QPushButton("Refresh Capture")
        self.refresh_capture_btn.setStyleSheet("""
            QPushButton {
                background-color: #344E7F;
                color: white;
                font-weight: bold;
                border: 1px solid #D4AF37;
                border-radius: 3px;
                padding: 8px;
            }
        """)
        self.refresh_capture_btn.clicked.connect(self.refresh_capture)
        preview_layout.addWidget(self.refresh_capture_btn)
        
        capture_layout.addWidget(preview_container, alignment=Qt.AlignCenter)
        capture_box.setLayout(capture_layout)
        problem_layout.addWidget(capture_box)
        
        problem_box.setLayout(problem_layout)
        top_layout.addWidget(problem_box)
        
        splitter.addWidget(top_widget)
        
        # Bottom part - debug log with WoW styling
        log_widget = QWidget()
        log_widget.setStyleSheet("background-color: #0F1929;")
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        
        log_box = QGroupBox("Debug Log")
        log_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        log_inner_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #0A101E;
                border: 1px solid #344E7F;
                border-radius: 3px;
                color: #CCCCCC;
                selection-background-color: #4A6EA5;
                font-family: Consolas, Courier, monospace;
            }
        """)
        log_inner_layout.addWidget(self.log_text)
        
        # Add clear log button
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #344E7F;
                color: white;
                border: 1px solid #D4AF37;
                border-radius: 3px;
                padding: 5px;
            }
        """)
        self.clear_log_btn.clicked.connect(self.log_text.clear)
        log_inner_layout.addWidget(self.clear_log_btn, alignment=Qt.AlignRight)
        
        log_box.setLayout(log_inner_layout)
        log_layout.addWidget(log_box)
        
        splitter.addWidget(log_widget)
        
        # Set initial sizes
        splitter.setSizes([350, 350])
        
        layout.addWidget(splitter)
    
    def init_runner_tab(self):
        """Initialize the runner tab with WoW-style interface."""
        layout = QVBoxLayout(self.runner_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Top status panel
        status_box = QGroupBox("Spell Automation Status")
        status_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        status_layout = QGridLayout()
        status_layout.setVerticalSpacing(10)
        status_layout.setHorizontalSpacing(20)
        
        # Status indicators
        status_layout.addWidget(QLabel("Current Status:"), 0, 0)
        self.status_label = QLabel("Not Running")
        self.status_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #FF4444;
        """)
        status_layout.addWidget(self.status_label, 0, 1)
        
        # Current spell with icon placeholder
        status_layout.addWidget(QLabel("Active Spell:"), 1, 0)
        
        spell_container = QWidget()
        spell_layout = QHBoxLayout(spell_container)
        spell_layout.setContentsMargins(0, 0, 0, 0)
        spell_layout.setSpacing(5)
        
        self.spell_icon = QLabel()
        self.spell_icon.setFixedSize(24, 24)
        self.spell_icon.setStyleSheet("background-color: transparent;")
        spell_layout.addWidget(self.spell_icon)
        
        self.current_spell_label = QLabel("None")
        self.current_spell_label.setStyleSheet("font-weight: bold; color: #FFD100;")
        spell_layout.addWidget(self.current_spell_label)
        spell_layout.addStretch()
        
        status_layout.addWidget(spell_container, 1, 1)
        
        # Toggle key with WoW keybind styling
        status_layout.addWidget(QLabel("Toggle Key:"), 2, 0)
        
        f3_key = QLabel("F3")
        f3_key.setStyleSheet("""
            background-color: #19294A;
            border: 1px solid #D4AF37;
            border-radius: 4px;
            padding: 3px 8px;
            font-weight: bold;
            color: #FFD100;
            min-width: 30px;
            text-align: center;
        """)
        status_layout.addWidget(f3_key, 2, 1)
        
        # Add warning about ENTER key (important for WoW chat)
        warning_label = QLabel("WARNING: Pressing ENTER in-game will send keys to chat!")
        warning_label.setStyleSheet("color: #FF6060; font-style: italic;")
        status_layout.addWidget(warning_label, 3, 0, 1, 2)
        
        status_box.setLayout(status_layout)
        layout.addWidget(status_box)
        
        # Middle section with preview
        middle_section = QHBoxLayout()
        
        # Preview group with WoW UI styling
        preview_box = QGroupBox("Live Spell Preview")
        preview_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        preview_layout = QVBoxLayout()
        
        self.live_preview = QLabel()
        self.live_preview.setFixedSize(150, 150)
        self.live_preview.setAlignment(Qt.AlignCenter)
        self.live_preview.setFrameShape(QFrame.Box)
        self.live_preview.setStyleSheet("""
            border: 2px solid #344E7F;
            background-color: #0F1929;
        """)
        
        preview_layout.addWidget(self.live_preview, alignment=Qt.AlignHCenter)
        preview_box.setLayout(preview_layout)
        middle_section.addWidget(preview_box)
        
        # Control panel
        control_box = QGroupBox("Automation Control")
        control_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        control_layout = QVBoxLayout()
        
        # Big start/stop button like a WoW action button
        self.start_stop_btn = QPushButton("START AUTOMATION")
        self.start_stop_btn.setMinimumHeight(50)
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #1F6032; /* Green background */
                color: white;
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #D4AF37;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2A8045;
            }
            QPushButton:pressed {
                background-color: #184D28;
            }
        """)
        self.start_stop_btn.clicked.connect(self.toggle_automation)
        control_layout.addWidget(self.start_stop_btn)
        
        # Status toggle button (emulates F3)
        self.toggle_status_btn = QPushButton("Toggle Active/Paused (F3)")
        self.toggle_status_btn.clicked.connect(lambda: keyboard.press_and_release('f3'))
        control_layout.addWidget(self.toggle_status_btn)
        
        control_box.setLayout(control_layout)
        middle_section.addWidget(control_box)
        
        layout.addLayout(middle_section)
        
        # Bottom section - instructions
        instruction_box = QGroupBox("Quick Guide")
        instruction_box.setStyleSheet("""
            QGroupBox {
                background-color: #192742;
                border: 2px solid #D4AF37;
                border-radius: 8px;
            }
        """)
        instruction_layout = QVBoxLayout()
        
        instructions = QLabel(
            "<b>How to use:</b><br>"
            "1. Ensure your setup and keybindings are configured<br>"
            "2. Click START AUTOMATION to begin<br>"
            "3. Press <b>F3</b> in-game to toggle automation active/paused<br>"
            "4. Watch the preview panel to see which spell is being detected<br>"
            "<br><i>Remember: This works best with Hekili addon's \"1-button mode\" settings</i>"
        )
        instructions.setTextFormat(Qt.RichText)
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #BBBBBB; padding: 5px;")
        instruction_layout.addWidget(instructions)
        instruction_box.setLayout(instruction_layout)
        layout.addWidget(instruction_box)
    
    def set_dark_theme(self):
        """Set dark theme for the application."""
        dark_palette = QPalette()
        
        # Set colors
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        
        self.setPalette(dark_palette)
    
    def load_config(self):
        """Load configuration from file or create default if not exists."""
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "config_path": CONFIG_PATH,
                "Class": "",
                "location": [0, 0]
            }
    
    def save_config(self):
        """Save configuration to file."""
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=4, sort_keys=True)
    
    def get_available_classes_specs(self):
        """Get all available class and spec combinations from img directory."""
        available = []
        if os.path.exists(IMG_DIR):
            for item in os.listdir(IMG_DIR):
                if os.path.isdir(os.path.join(IMG_DIR, item)):
                    available.append(item)
        return sorted(available)
    
    def select_region(self):
        """Allow user to select a region of the screen."""
        self.setWindowState(self.windowState() | Qt.WindowMinimized)
        QApplication.processEvents()
        time.sleep(0.5)  # Small delay to ensure window is minimized
        
        # Capture the screen
        screenshot = pyautogui.screenshot()
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # Selection variables
        selecting = False
        start_x, start_y = 0, 0
        end_x, end_y = 0, 0
        selection = None
        
        def mouse_callback(event, x, y, flags, param):
            nonlocal selecting, start_x, start_y, end_x, end_y, selection
            
            if event == cv2.EVENT_LBUTTONDOWN:
                selecting = True
                start_x, start_y = x, y
                end_x, end_y = x, y
            
            elif event == cv2.EVENT_MOUSEMOVE and selecting:
                end_x, end_y = x, y
            
            elif event == cv2.EVENT_LBUTTONUP:
                selecting = False
                selection = (
                    min(start_x, end_x),
                    min(start_y, end_y),
                    abs(end_x - start_x),
                    abs(end_y - start_y)
                )
        
        window_name = "Select Hekili Spellbox Region (Press 'q' to exit)"
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, mouse_callback)
        
        while True:
            img = screenshot.copy()
            if selecting or selection:
                x1, y1 = min(start_x, end_x), min(start_y, end_y)
                x2, y2 = max(start_x, end_x), max(start_y, end_y)
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            cv2.imshow(window_name, img)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                break
        
        cv2.destroyAllWindows()
        
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.activateWindow()
        
        if selection:
            self.box_position = selection
            self.region_label.setText(f"{selection[0]}, {selection[1]}, {selection[2]}x{selection[3]}")
            self.log(f"Selected region: {selection}")
    
    def apply_setup(self):
        """Apply and save the setup configuration."""
        if not self.box_position:
            QMessageBox.warning(self, "Setup Error", "Please select a screen region first.")
            return
        
        class_spec = self.class_combo.currentText()
        if not class_spec:
            QMessageBox.warning(self, "Setup Error", "Please select a class/spec first.")
            return
        
        # Save configuration
        self.config["Class"] = class_spec
        self.config["location"] = [self.box_position[0], self.box_position[1]]
        self.save_config()
        
        # Load spell info
        self.spell_info = self.get_spells_for_class_spec(class_spec)
        self.populate_keybindings()
        
        self.log(f"Setup applied for {class_spec}")
        self.statusBar().showMessage(f"Setup applied for {class_spec}")
        
        # Switch to keybindings tab
        self.tab_widget.setCurrentWidget(self.config_tab)
    
    def get_spells_for_class_spec(self, class_spec):
        """Get all spell images for the selected class/spec."""
        spell_dir = os.path.join(IMG_DIR, class_spec)
        spells = {}
        
        if os.path.exists(spell_dir):
            for file in os.listdir(spell_dir):
                if file.endswith(('.jpg', '.jpeg', '.png')):
                    spell_name = os.path.splitext(file)[0]
                    spells[spell_name] = {
                        "icon_path": os.path.join(spell_dir, file),
                        "key": ""
                    }
        
        return spells
    
    def populate_keybindings(self):
        """Populate the keybinding grid with current spell info and WoW styling."""
        # Clear existing widgets (removing everything except header row)
        for i in reversed(range(1, self.keybind_layout.rowCount())):
            for j in range(self.keybind_layout.columnCount()):
                widget = self.keybind_layout.itemAtPosition(i, j)
                if widget and widget.widget():
                    widget.widget().deleteLater()
        
        self.keybind_inputs = {}
        
        # Get existing keybindings if available
        if "keybindings" in self.config:
            for spell_name, key in self.config["keybindings"].items():
                if spell_name in self.spell_info:
                    self.spell_info[spell_name]["key"] = key
        
        # Create inputs for each spell
        row = 1  # Start after header row
        for spell_name in sorted(self.spell_info.keys()):
            # Create spell name container with icon
            spell_container = QWidget()
            
            # Set alternating row background colors
            if row % 2 == 0:
                spell_container.setStyleSheet("background-color: #192742;")
            else:
                spell_container.setStyleSheet("background-color: #0F1929;")
            
            spell_layout = QHBoxLayout(spell_container)
            spell_layout.setContentsMargins(5, 5, 5, 5)
            spell_layout.setSpacing(10)
            
            # Add spell icon if available
            icon_path = self.spell_info[spell_name]["icon_path"]
            if os.path.exists(icon_path):
                icon_label = QLabel()
                img = Image.open(icon_path)
                img = img.resize((24, 24), Image.LANCZOS)
                qimg = pil_to_qimage(img)
                pixmap = QPixmap.fromImage(qimg)
                icon_label.setPixmap(pixmap)
                spell_layout.addWidget(icon_label)
            
            # Add spell name label
            name_label = QLabel(spell_name)
            name_label.setStyleSheet("color: #FFD100; font-weight: bold;")
            spell_layout.addWidget(name_label)
            spell_layout.addStretch()
            
            self.keybind_layout.addWidget(spell_container, row, 0)
            
            # Create input container
            input_container = QWidget()
            if row % 2 == 0:
                input_container.setStyleSheet("background-color: #192742;")
            else:
                input_container.setStyleSheet("background-color: #0F1929;")
            
            input_layout = QHBoxLayout(input_container)
            input_layout.setContentsMargins(5, 5, 5, 5)
            
            # Add input field with WoW styling
            key_input = QLineEdit()
            key_input.setText(self.spell_info[spell_name]["key"])
            key_input.setStyleSheet("""
                QLineEdit {
                    background-color: #19294A;
                    border: 1px solid #344E7F;
                    border-radius: 3px;
                    padding: 5px;
                    color: #FFD100;
                    font-weight: bold;
                    selection-background-color: #4A6EA5;
                    max-width: 150px;
                }
            """)
            key_input.setAlignment(Qt.AlignCenter)
            input_layout.addWidget(key_input, alignment=Qt.AlignCenter)
            
            self.keybind_inputs[spell_name] = key_input
            self.keybind_layout.addWidget(input_container, row, 1)
            
            row += 1
        
        # Set column stretches
        self.keybind_layout.setColumnStretch(0, 3)  # Spell name gets more space
        self.keybind_layout.setColumnStretch(1, 1)  # Key binding gets less space
    
    def save_keybindings(self):
        """Save keybindings to configuration."""
        keybindings = {}
        for spell_name, input_field in self.keybind_inputs.items():
            value = input_field.text().strip()
            if value and value.lower() != "skip":
                self.spell_info[spell_name]["key"] = value
                keybindings[spell_name] = value
        
        self.config["keybindings"] = keybindings
        self.save_config()
        
        self.log("Keybindings saved")
        self.statusBar().showMessage("Keybindings saved")
    
    def reset_keybindings(self):
        """Reset all keybindings."""
        for input_field in self.keybind_inputs.values():
            input_field.setText("")
        
        self.log("Keybindings reset")
    
    def load_existing_config(self):
        """Load existing configuration if available."""
        if "Class" in self.config and self.config["Class"]:
            # Set class dropdown
            idx = self.class_combo.findText(self.config["Class"])
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)
            
            # Set region if available
            if "location" in self.config and len(self.config["location"]) >= 2:
                x, y = self.config["location"]
                width, height = 50, 50  # Default size
                self.box_position = (x, y, width, height)
                self.region_label.setText(f"{x}, {y}, {width}x{height}")
            
            # Load spell info
            self.spell_info = self.get_spells_for_class_spec(self.config["Class"])
            self.populate_keybindings()
            
            self.log(f"Loaded existing configuration for {self.config['Class']}")
    
    def update_threshold_label(self):
        """Update the threshold label when slider changes."""
        value = self.threshold_slider.value()
        self.threshold_label.setText(str(value))
    
    def refresh_capture(self):
        """Capture and display the current Hekili spellbox."""
        if not self.box_position:
            QMessageBox.warning(self, "Error", "Please select a screen region first.")
            return
        
        try:
            # Capture the region
            left, top, width, height = self.box_position
            region = (left, top, left + width, top + height)
            screenshot = ImageGrab.grab(bbox=region)
            
            # Convert to QPixmap and display
            qimg = pil_to_qimage(screenshot)
            pixmap = QPixmap.fromImage(qimg)
            
            # Resize if needed
            if pixmap.width() > 100 or pixmap.height() > 100:
                pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.preview_label.setPixmap(pixmap)
            
            # Save for debugging
            os.makedirs(DEBUG_DIR, exist_ok=True)
            screenshot.save(os.path.join(DEBUG_DIR, "manual_capture.png"))
            
            self.log("Captured current screen region")
        except Exception as e:
            self.log(f"Error capturing screen: {e}")
    
    def test_spell_recognition(self, spell_to_test):
        """Test recognition for a specific spell."""
        if not self.box_position or not self.spell_info:
            QMessageBox.warning(self, "Error", "Please configure class and screen region first.")
            return
        
        # Clear previous logs related to testing
        self.log("----------------")
        self.log(f"Starting test for {spell_to_test}")
        
        # Create and start test thread
        self.test_thread = SpellTestThread(
            self.box_position, 
            self.spell_info, 
            spell_to_test,
            self.threshold_slider.value()
        )
        self.test_thread.update_signal.connect(self.log)
        self.test_thread.image_signal.connect(self.update_preview)
        self.test_thread.start()
    
    def toggle_automation(self):
        """Start or stop the automation with enhanced visual feedback."""
        if not self.capture_thread or not self.capture_thread.running:
            # Start automation
            if not self.box_position or not self.spell_info:
                QMessageBox.warning(self, "Setup Error", "Please configure class, screen region, and keybindings first.")
                return
            
            # Check if we have any keybindings configured
            has_keybindings = False
            for info in self.spell_info.values():
                if "key" in info and info["key"]:
                    has_keybindings = True
                    break
            
            if not has_keybindings:
                QMessageBox.warning(self, "Setup Error", "No keybindings configured. Please set up keybindings first.")
                return
            
            # Log problem spells
            problem_spells = ["storm_elemental", "ascendance"]
            found_problems = False
            self.log("----------------")
            self.log("Starting automation")
            
            for problem in problem_spells:
                for spell_name, info in self.spell_info.items():
                    if problem.lower() in spell_name.lower():
                        found_problems = True
                        self.log(f"Special handling for: {spell_name} (Keybind: {info['key']})")
            
            if not found_problems:
                self.log("Warning: No problem spells (Storm Elemental/Ascendance) found.")
            
            # Start capture thread
            self.capture_thread = CaptureThread(
                self.box_position, 
                self.spell_info,
                self.threshold_slider.value()
            )
            self.capture_thread.update_signal.connect(self.log)
            self.capture_thread.spell_signal.connect(self.update_current_spell)
            self.capture_thread.image_signal.connect(self.update_live_preview)
            self.capture_thread.start()
            
            # Update UI with WoW styling for "running" state
            self.start_stop_btn.setText("STOP AUTOMATION")
            self.start_stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #722424; /* Red background for stop */
                    color: white;
                    font-weight: bold;
                    font-size: 14px;
                    border: 2px solid #D4AF37;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #9B3232;
                }
            """)
            self.status_label.setText("Running")
            self.status_label.setStyleSheet("""
                font-size: 14px;
                font-weight: bold;
                color: #40FF40; /* Green for running */
            """)
            self.statusBar().showMessage("Automation started")
        else:
            # Stop automation
            if self.capture_thread:
                self.capture_thread.stop()
                self.log("Automation stopped")
                
                # Update UI with WoW styling for "stopped" state
                self.start_stop_btn.setText("START AUTOMATION")
                self.start_stop_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1F6032; /* Green background for start */
                        color: white;
                        font-weight: bold;
                        font-size: 14px;
                        border: 2px solid #D4AF37;
                        border-radius: 5px;
                    }
                    QPushButton:hover {
                        background-color: #2A8045;
                    }
                """)
                self.status_label.setText("Not Running")
                self.status_label.setStyleSheet("""
                    font-size: 14px;
                    font-weight: bold;
                    color: #FF4444; /* Red for not running */
                """)
                self.current_spell_label.setText("None")
                self.spell_icon.clear()
                self.statusBar().showMessage("Automation stopped")
    
    def update_current_spell(self, spell_name):
        """Update the current spell label and icon."""
        self.current_spell_label.setText(spell_name)
        
        # Update the spell icon if available
        if spell_name in self.spell_info:
            icon_path = self.spell_info[spell_name]["icon_path"]
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                img = img.resize((24, 24), Image.LANCZOS)
                qimg = pil_to_qimage(img)
                pixmap = QPixmap.fromImage(qimg)
                self.spell_icon.setPixmap(pixmap)
        else:
            self.spell_icon.clear()
    
    def update_preview(self, qimg):
        """Update the preview label with a QImage."""
        pixmap = QPixmap.fromImage(qimg)
        if pixmap.width() > 100 or pixmap.height() > 100:
            pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(pixmap)
    
    def update_live_preview(self, qimg):
        """Update the live preview in the runner tab."""
        pixmap = QPixmap.fromImage(qimg)
        if pixmap.width() > 150 or pixmap.height() > 150:
            pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.live_preview.setPixmap(pixmap)
    
    def log(self, message):
        """Add a message to the log with WoW-style coloring."""
        timestamp = time.strftime("%H:%M:%S")
        
        # Apply color based on message content
        if "error" in message.lower() or "warning" in message.lower():
            # Red text for errors and warnings
            formatted_message = f"<span style='color: #FF6060;'>[{timestamp}] {message}</span>"
        elif "found" in message.lower() or "detected" in message.lower() or "match" in message.lower():
            # Green text for successful detections
            formatted_message = f"<span style='color: #40FF40;'>[{timestamp}] {message}</span>"
        elif "special handling" in message.lower():
            # Purple text for special handling messages
            formatted_message = f"<span style='color: #FF80FF;'>[{timestamp}] {message}</span>"
        elif "starting" in message.lower():
            # Gold text for important status changes
            formatted_message = f"<span style='color: #FFD100; font-weight: bold;'>[{timestamp}] {message}</span>"
        else:
            # Default color
            formatted_message = f"<span style='color: #CCCCCC;'>[{timestamp}] {message}</span>"
        
        self.log_text.append(formatted_message)
        
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def closeEvent(self, event):
        """Handle application close event."""
        if self.capture_thread and self.capture_thread.running:
            self.capture_thread.stop()
        event.accept()


def main():
    # Ensure required directories exist
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)
    
    app = QApplication(sys.argv)
    window = AutoHekiliGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()