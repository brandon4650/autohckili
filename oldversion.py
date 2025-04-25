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
        
    
    def init_setup_tab(self):
        """Initialize the setup tab."""
        layout = QVBoxLayout(self.setup_tab)
        
        # Introduction
        intro_box = QGroupBox("Welcome to AUTO_Hekili")
        intro_layout = QVBoxLayout()
        intro_text = QLabel(
            "This application will automate spell casting based on Hekili addon recommendations.\n\n"
            "WARNING: Using automation tools may violate World of Warcraft's Terms of Service.\n"
            "Use at your own risk!"
        )
        intro_text.setWordWrap(True)
        intro_layout.addWidget(intro_text)
        intro_box.setLayout(intro_layout)
        layout.addWidget(intro_box)
        
        # Class and spec selection
        class_box = QGroupBox("Class & Specialization")
        class_layout = QFormLayout()
        
        self.class_combo = QComboBox()
        self.class_combo.addItems(self.get_available_classes_specs())
        if "Class" in self.config and self.config["Class"]:
            idx = self.class_combo.findText(self.config["Class"])
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)
        
        class_layout.addRow("Select Class/Spec:", self.class_combo)
        class_box.setLayout(class_layout)
        layout.addWidget(class_box)
        
        # Screen region selection
        region_box = QGroupBox("Hekili Spellbox Region")
        region_layout = QFormLayout()
        
        region_btn_layout = QHBoxLayout()
        self.region_label = QLabel("Not selected")
        self.select_region_btn = QPushButton("Select Region")
        self.select_region_btn.clicked.connect(self.select_region)
        region_btn_layout.addWidget(self.region_label)
        region_btn_layout.addWidget(self.select_region_btn)
        
        region_layout.addRow("Spellbox Region:", region_btn_layout)
        region_box.setLayout(region_layout)
        layout.addWidget(region_box)
        
        # Apply button
        self.apply_btn = QPushButton("Apply Setup")
        self.apply_btn.clicked.connect(self.apply_setup)
        layout.addWidget(self.apply_btn)
        
        # Add spacer
        layout.addStretch()
    
    def init_config_tab(self):
        """Initialize the configuration tab."""
        layout = QVBoxLayout(self.config_tab)
        
        # Create a scroll area for keybindings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.keybind_widget = QWidget()
        self.keybind_layout = QFormLayout(self.keybind_widget)
        scroll.setWidget(self.keybind_widget)
        
        # Add instructions
        instructions = QLabel(
            "Configure keybindings for your spells. These must match your in-game keybindings.\n"
            "Leave empty or type 'skip' to ignore spells you don't use.\n"
            "For modifier keys, use: alt+key, ctrl+key, shift+key (e.g., 'alt+1', 'ctrl+f')"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Add scroll area
        layout.addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.save_keybinds_btn = QPushButton("Save Keybindings")
        self.save_keybinds_btn.clicked.connect(self.save_keybindings)
        self.reset_keybinds_btn = QPushButton("Reset All")
        self.reset_keybinds_btn.clicked.connect(self.reset_keybindings)
        btn_layout.addWidget(self.save_keybinds_btn)
        btn_layout.addWidget(self.reset_keybinds_btn)
        layout.addLayout(btn_layout)
    
    def init_debug_tab(self):
        """Initialize the debug tab."""
        layout = QVBoxLayout(self.debug_tab)
        
        # Split the debug tab into two parts
        splitter = QSplitter(Qt.Vertical)
        
        # Top part - testing controls
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        # Problem spell testing
        problem_box = QGroupBox("Test Problematic Spells")
        problem_layout = QVBoxLayout()
        
        # Instructions
        test_instructions = QLabel(
            "Test recognition for problematic spells like Storm Elemental and Ascendance.\n"
            "Make sure Hekili is showing the spell you want to test before clicking the test button."
        )
        test_instructions.setWordWrap(True)
        problem_layout.addWidget(test_instructions)
        
        # Test buttons for specific problem spells
        btn_layout = QHBoxLayout()
        self.test_storm_btn = QPushButton("Test Storm Elemental")
        self.test_storm_btn.clicked.connect(lambda: self.test_spell_recognition("storm_elemental"))
        self.test_ascendance_btn = QPushButton("Test Ascendance")
        self.test_ascendance_btn.clicked.connect(lambda: self.test_spell_recognition("ascendance"))
        btn_layout.addWidget(self.test_storm_btn)
        btn_layout.addWidget(self.test_ascendance_btn)
        problem_layout.addLayout(btn_layout)
        
        # Threshold adjustment
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Recognition Threshold:"))
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(5)
        self.threshold_slider.setMaximum(25)
        self.threshold_slider.setValue(15)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(5)
        self.threshold_label = QLabel("15")
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)
        threshold_layout.addWidget(self.threshold_slider)
        threshold_layout.addWidget(self.threshold_label)
        problem_layout.addLayout(threshold_layout)
        
        # Capture preview
        capture_layout = QHBoxLayout()
        capture_layout.addWidget(QLabel("Current Capture:"))
        self.refresh_capture_btn = QPushButton("Refresh")
        self.refresh_capture_btn.clicked.connect(self.refresh_capture)
        capture_layout.addWidget(self.refresh_capture_btn)
        problem_layout.addLayout(capture_layout)
        
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(100, 100)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFrameShape(QFrame.Box)
        problem_layout.addWidget(self.preview_label, alignment=Qt.AlignHCenter)
        
        problem_box.setLayout(problem_layout)
        top_layout.addWidget(problem_box)
        
        splitter.addWidget(top_widget)
        
        # Bottom part - debug log
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        
        log_layout.addWidget(QLabel("Debug Log:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        splitter.addWidget(log_widget)
        
        # Set initial sizes
        splitter.setSizes([300, 400])
        
        layout.addWidget(splitter)
    
    def init_runner_tab(self):
        """Initialize the runner tab."""
        layout = QVBoxLayout(self.runner_tab)
        
        # Status group
        status_box = QGroupBox("Automation Status")
        status_layout = QGridLayout()
        
        status_layout.addWidget(QLabel("Status:"), 0, 0)
        self.status_label = QLabel("Not Running")
        status_layout.addWidget(self.status_label, 0, 1)
        
        status_layout.addWidget(QLabel("Current Spell:"), 1, 0)
        self.current_spell_label = QLabel("None")
        status_layout.addWidget(self.current_spell_label, 1, 1)
        
        status_layout.addWidget(QLabel("Toggle Key:"), 2, 0)
        status_layout.addWidget(QLabel("F3"), 2, 1)
        
        status_box.setLayout(status_layout)
        layout.addWidget(status_box)
        
        # Preview group
        preview_box = QGroupBox("Live Preview")
        preview_layout = QVBoxLayout()
        
        self.live_preview = QLabel()
        self.live_preview.setFixedSize(150, 150)
        self.live_preview.setAlignment(Qt.AlignCenter)
        self.live_preview.setFrameShape(QFrame.Box)
        
        preview_layout.addWidget(self.live_preview, alignment=Qt.AlignHCenter)
        preview_box.setLayout(preview_layout)
        layout.addWidget(preview_box)
        
        # Button group
        btn_box = QGroupBox("Control")
        btn_layout = QVBoxLayout()
        
        self.start_stop_btn = QPushButton("Start Automation")
        self.start_stop_btn.clicked.connect(self.toggle_automation)
        btn_layout.addWidget(self.start_stop_btn)
        
        btn_box.setLayout(btn_layout)
        layout.addWidget(btn_box)
        
        # Instructions
        instructions = QLabel(
            "Instructions:\n"
            "1. Configure your setup in the Setup tab\n"
            "2. Set keybindings in the Keybindings tab\n"
            "3. Test problematic spells in the Debug tab if needed\n"
            "4. Click 'Start Automation' to begin\n"
            "5. Press F3 at any time to toggle automation on/off"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Add spacer
        layout.addStretch()
    
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
        """Populate the keybinding form with current spell info."""
        # Clear existing widgets
        while self.keybind_layout.rowCount() > 0:
            self.keybind_layout.removeRow(0)
        
        self.keybind_inputs = {}
        
        # Get existing keybindings if available
        if "keybindings" in self.config:
            for spell_name, key in self.config["keybindings"].items():
                if spell_name in self.spell_info:
                    self.spell_info[spell_name]["key"] = key
        
        # Create inputs for each spell
        for spell_name in sorted(self.spell_info.keys()):
            # Create horizontal layout for spell
            row_layout = QHBoxLayout()
            
            # Add spell icon if available
            icon_path = self.spell_info[spell_name]["icon_path"]
            if os.path.exists(icon_path):
                icon_label = QLabel()
                img = Image.open(icon_path)
                img = img.resize((24, 24), Image.LANCZOS)
                qimg = pil_to_qimage(img)
                pixmap = QPixmap.fromImage(qimg)
                icon_label.setPixmap(pixmap)
                row_layout.addWidget(icon_label)
            
            # Add input field
            key_input = QLineEdit()
            key_input.setText(self.spell_info[spell_name]["key"])
            self.keybind_inputs[spell_name] = key_input
            row_layout.addWidget(key_input)
            
            # Add row to form
            self.keybind_layout.addRow(spell_name, row_layout)
    
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
        """Start or stop the automation."""
        if not self.capture_thread or not self.capture_thread.running:
            # Start automation
            if not self.box_position or not self.spell_info:
                QMessageBox.warning(self, "Error", "Please configure class, screen region, and keybindings first.")
                return
            
            # Check if we have any keybindings configured
            has_keybindings = False
            for info in self.spell_info.values():
                if "key" in info and info["key"]:
                    has_keybindings = True
                    break
            
            if not has_keybindings:
                QMessageBox.warning(self, "Error", "No keybindings configured. Please set up keybindings first.")
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
            
            # Update UI
            self.start_stop_btn.setText("Stop Automation")
            self.status_label.setText("Running")
            self.statusBar().showMessage("Automation started")
        else:
            # Stop automation
            if self.capture_thread:
                self.capture_thread.stop()
                self.log("Automation stopped")
                
                # Update UI
                self.start_stop_btn.setText("Start Automation")
                self.status_label.setText("Not Running")
                self.current_spell_label.setText("None")
                self.statusBar().showMessage("Automation stopped")
    
    def update_current_spell(self, spell_name):
        """Update the current spell label."""
        self.current_spell_label.setText(spell_name)
    
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
        """Add a message to the log."""
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.log_text.append(log_message)
        
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