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
from tkinter import Tk
from tkinter.filedialog import askdirectory
from os import listdir
from os.path import isfile, join

# Constants
CONFIG_PATH = "config\\config.json"
IMG_DIR = "img"
SIMC_NOTES_DIR = "config\\Notes"

def load_config():
    """Load configuration from file or create default if not exists."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "config_path": CONFIG_PATH,
            "Class": "Death_Knight_Blood",
            "location": [0, 0]
        }

def save_config(config):
    """Save configuration to file."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4, sort_keys=True)

def get_all_classes_specs():
    """Get all class/spec combinations from simc files, supporting both 90_ and TWW1_ prefixes."""
    mypath = SIMC_NOTES_DIR
    class_specs = set()
    
    for f in listdir(mypath):
        if isfile(join(mypath, f)) and f.endswith(".simc"):
            base_name = None
            
            # Handle 90_ prefix files
            if f.startswith("90_"):
                base_name = f.replace("90_", "").replace(".simc", "")
                
            # Handle TWW1_ prefix files
            elif f.startswith("TWW1_"):
                class_parts = f.replace("TWW1_", "").replace(".simc", "").split("_")
                
                if len(class_parts) >= 2:
                    class_name = class_parts[0]
                    spec_name = class_parts[1]
                    
                    # Handle special cases like Beast_Mastery
                    if class_name == "Hunter" and spec_name == "Beast":
                        base_name = "Hunter_BeastMastery"
                    else:
                        # For specs with multiple variant builds, use only the base spec name
                        base_name = f"{class_name}_{spec_name}"
            
            if base_name:
                class_specs.add(base_name)
    
    result = list(class_specs)
    result.sort()
    return result

def get_available_classes_specs():
    """Get all available class and spec combinations from img directory."""
    available = []
    for item in os.listdir(IMG_DIR):
        if os.path.isdir(os.path.join(IMG_DIR, item)):
            available.append(item)
    return sorted(available)

def get_spells_from_class_spec(class_spec):
    """Extract spells from simc file for the given class/spec, handling both file formats."""
    spells = []
    file_path = None
    mypath = SIMC_NOTES_DIR
    
    # SimC directives to filter out
    simc_directives = [
        "call_action_list", "run_action_list", "use_item", "use_items",
        "variable", "pool_resource", "wait", "potion", "cancel_buff",
        "snapshot_stats", "invoke_external_buff"
    ]
    
    # Try to find a matching TWW1 file first
    tww1_files = []
    for f in listdir(mypath):
        if isfile(join(mypath, f)) and f.endswith(".simc") and f.startswith(f"TWW1_{class_spec.split('_')[0]}_{class_spec.split('_')[1]}"):
            tww1_files.append(f)
    
    # If TWW1 files found, use the first one
    if tww1_files:
        file_path = join(mypath, tww1_files[0])
        print(f"Using TWW1 file for {class_spec}: {tww1_files[0]}")
    else:
        # Fall back to the 90_ format
        file_path = join(mypath, f"90_{class_spec}.simc")
        if not isfile(file_path):
            print(f"Warning: No SIMC file found for {class_spec}")
            return []
    
    # Read the file and extract spells
    with open(file_path) as f:
        for line in f:
            if "actions" not in line:
                continue
                
            # Handle different action line formats
            if "actions" in line and "=" in line:
                # For TWW1_ complex action format
                if re.search(r'actions[^=]*=/[a-z_]*', line):
                    match = re.search(r'=/[a-z_]*', line)
                    if match:
                        spell = match.group().split("=/")[-1]
                        # Skip SimC directives and auto_attack
                        if spell and spell not in spells and spell != "auto_attack" and spell not in simc_directives:
                            spells.append(spell)
                # For 90_ simpler action format
                else:
                    action_parts = line.split("=")
                    if len(action_parts) > 1:
                        spell_part = action_parts[1].split(",")[0]
                        spell = spell_part.strip()
                        # Skip SimC directives and auto_attack
                        if spell and spell not in spells and spell != "auto_attack" and spell not in simc_directives:
                            spells.append(spell)
    
    spells.sort()
    return spells

def select_screen_region():
    """Allow user to select a region of the screen."""
    print("Selecting screen region for Hekili spellbox...")
    print("Press and hold the left mouse button to select a region.")
    print("Press 'q' to exit selection mode.")
    
    # Take a screenshot for selection
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
    return selection

def select_class_and_spec():
    """Allow user to select class and specialization from available options."""
    available = get_all_classes_specs()
    
    # Group by class
    classes = {}
    for class_spec in available:
        parts = class_spec.split('_')
        if len(parts) >= 2:
            class_name = parts[0]
            spec_name = '_'.join(parts[1:])
            if class_name not in classes:
                classes[class_name] = []
            classes[class_name].append(spec_name)
    
    # Display class options
    print("\nSelect your class:")
    class_list = sorted(list(classes.keys()))
    for i, class_name in enumerate(class_list, 1):
        print(f"{i}. {class_name}")
    
    while True:
        try:
            choice = int(input("Enter class number: "))
            if 1 <= choice <= len(class_list):
                selected_class = class_list[choice - 1]
                break
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Please enter a number.")
    
    # Display spec options
    print(f"\nSelect your {selected_class} specialization:")
    specs = classes[selected_class]
    for i, spec in enumerate(specs, 1):
        print(f"{i}. {spec}")
    
    while True:
        try:
            choice = int(input("Enter specialization number: "))
            if 1 <= choice <= len(specs):
                selected_spec = specs[choice - 1]
                break
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Please enter a number.")
    
    return f"{selected_class}_{selected_spec}"

def get_spells_for_class_spec(class_spec):
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

def configure_keybindings(spells):
    """Allow user to configure keybindings for spells with option to skip spells and support for modifier keys."""
    print("\nConfigure keybindings for your spells:")
    print("These should match your in-game keybindings [[1]](https://poe.com/citation?message_id=380869619859&citation=1).")
    print("Type 'skip' to ignore spells you don't use (like racials or unavailable covenant abilities)")
    print("For special key combinations, use: alt+key, ctrl+key, shift+key (e.g., 'alt+1', 'ctrl+f')")
    
    for spell_name in sorted(spells.keys()):
        while True:
            key_input = input(f"Enter key for {spell_name} (or type 'skip' to ignore this spell): ")
            
            if key_input.lower() == 'skip':
                print(f"Skipping {spell_name}")
                # Remove this spell from the dictionary
                spells.pop(spell_name)
                break
            elif key_input.strip():
                # Store the keybind
                spells[spell_name]["key"] = key_input.strip()
                break
            else:
                print("Invalid key. Try again.")
    
    return spells

def press_key_combination(key_combo):
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


def capture_and_compare(box_position, spell_info, stop_event):
    """Capture screen region and compare with spell icons."""
    print("Starting automation. Press F3 to toggle on/off.")
    active = True
    
    # Create debug directory
    debug_dir = "debug_captures"
    os.makedirs(debug_dir, exist_ok=True)
    
    # Special handling for problematic spells
    problem_spells = ["storm_elemental", "ascendance"]
    problem_spell_info = {s: info for s, info in spell_info.items() if s.lower() in problem_spells}
    
    # Print debug info for problem spells
    for spell_name, info in problem_spell_info.items():
        print(f"Special handling enabled for: {spell_name}")
        print(f"  - Icon path: {info['icon_path']}")
        print(f"  - Keybind: {info['key']}")
        if os.path.exists(info["icon_path"]):
            img = Image.open(info["icon_path"])
            img.save(os.path.join(debug_dir, f"reference_{spell_name}.png"))
    
    spell_hashes = {}
    for spell_name, info in spell_info.items():
        if os.path.exists(info["icon_path"]):
            try:
                img = Image.open(info["icon_path"])
                spell_hashes[spell_name] = imagehash.phash(img)
            except Exception as e:
                print(f"Error loading image for {spell_name}: {e}")
    
    capture_count = 0
    last_spell = None
    
    while not stop_event.is_set():
        if keyboard.is_pressed('f3'):
            active = not active
            status = "activated" if active else "paused"
            print(f"Automation {status}")
            time.sleep(0.3)  # Debounce
            
        if active:
            try:
                # Capture the screen region
                left, top, width, height = box_position
                region = (left, top, left + width, top + height)
                screenshot = ImageGrab.grab(bbox=region)
                
                # Save occasional screenshots for debugging
                if capture_count % 100 == 0:
                    screenshot.save(os.path.join(debug_dir, f"capture_{capture_count}.png"))
                    
                # First try template matching for problematic spells
                problem_spell_matched = False
                for spell_name, info in problem_spell_info.items():
                    # Convert to CV2 format
                    screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                    template = cv2.imread(info["icon_path"])
                    
                    if template is not None:
                        # Use template matching
                        result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                        
                        # If strong match found (threshold can be adjusted)
                        if max_val >= 0.7:
                            # Save this detection
                            if spell_name != last_spell:
                                print(f"Template matching found: {spell_name} (confidence: {max_val:.2f})")
                                screenshot.save(os.path.join(debug_dir, f"detected_{spell_name}_{capture_count}.png"))
                                last_spell = spell_name
                            
                            # Press the key
                            key = info["key"]
                            if key:
                                press_key_combination(key)
                                time.sleep(0.1)  # Small delay to prevent key spamming
                            
                            problem_spell_matched = True
                            break
                
                # If no problem spell was found, use the regular phash method
                if not problem_spell_matched:
                    # Compare with spell icons
                    current_hash = imagehash.phash(screenshot)
                    best_match = None
                    min_diff = float('inf')
                    
                    for spell_name, phash in spell_hashes.items():
                        diff = phash - current_hash
                        if diff < min_diff:
                            min_diff = diff
                            best_match = spell_name
                    
                    # If a match is found and it's close enough
                    if best_match and min_diff < 15:  # Standard threshold
                        # Only log when spell changes
                        if best_match != last_spell:
                            print(f"Hash matching found: {best_match} (diff: {min_diff})")
                            last_spell = best_match
                        
                        key = spell_info[best_match]["key"]
                        if key:
                            press_key_combination(key)
                            time.sleep(0.1)  # Small delay to prevent key spamming
                
                capture_count += 1
                time.sleep(0.05)  # Small delay between captures
            except Exception as e:
                print(f"Error in capture and compare: {e}")
                time.sleep(1)
        else:
            time.sleep(0.1)

def test_spell_recognition(spell_info, box_position):
    """Test recognition for specific problematic spells."""
    problem_spells = ["storm_elemental", "ascendance"]
    test_spells = {s: info for s, info in spell_info.items() if s.lower() in problem_spells}
    
    if not test_spells:
        print("No problematic spells found in your configuration.")
        return
    
    print("\nRunning recognition test for problematic spells...")
    debug_dir = "debug_captures"
    os.makedirs(debug_dir, exist_ok=True)
    
    for spell_name, info in test_spells.items():
        print(f"Testing recognition for: {spell_name}")
        print(f"  - Icon path: {info['icon_path']}")
        print(f"  - Keybind: {info['key']}")
        
        # Take a screenshot of the target area
        left, top, width, height = box_position
        region = (left, top, left + width, top + height)
        screenshot = ImageGrab.grab(bbox=region)
        screenshot.save(os.path.join(debug_dir, f"test_capture_{spell_name}.png"))
        
        # Try both recognition methods
        
        # 1. Hash comparison
        ref_img = Image.open(info["icon_path"])
        ref_hash = imagehash.phash(ref_img)
        current_hash = imagehash.phash(screenshot)
        hash_diff = ref_hash - current_hash
        
        print(f"  Hash comparison result: diff = {hash_diff} (lower is better, < 15 needed)")
        
        # 2. Template matching
        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        template = cv2.imread(info["icon_path"])
        if template is not None:
            result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            print(f"  Template matching result: confidence = {max_val:.2f} (higher is better, > 0.7 needed)")
        else:
            print(f"  Could not load template image for CV2: {info['icon_path']}")
    
    print("\nTest completed. Screenshots saved to debug_captures directory.")

def main():
    """Main entry point of the application."""
    print("====== Auto_Hekili (Console Version) ======")
    print("This program will automate spell casting based on Hekili addon recommendations.")
    print("WARNING: Using automation tools may violate World of Warcraft's Terms of Service.")
    print("Use at your own risk!")
    
    # Check if img directory exists
    if not os.path.exists(IMG_DIR):
        print(f"Error: '{IMG_DIR}' directory not found.")
        print("Make sure you're running this script from the Auto_Hekili root directory.")
        return
    
    # Ensure config directory exists
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    
    config = load_config()
    
    # Check if we have an existing valid configuration we can reuse
    reuse_config = False
    if "Class" in config and "location" in config and "keybindings" in config:
        print(f"\nExisting configuration found for: {config['Class']}")
        print(f"Screen region: {config['location']}")
        print(f"Number of keybindings: {len(config['keybindings'])}")
        
        while True:
            reuse = input("Would you like to reuse this configuration? (y/n): ")
            if reuse.lower() == 'y':
                reuse_config = True
                break
            elif reuse.lower() == 'n':
                break
            else:
                print("Invalid input. Please enter 'y' or 'n'.")
    
    if reuse_config:
        # Use existing configuration
        print("\nReusing existing configuration.")
        class_spec = config["Class"]
        
        # Get the screen region from config
        box_position = (
            config["location"][0], 
            config["location"][1],
            50,  # Default width if not specified
            50   # Default height if not specified
        )
        
        # Load all spells for the class/spec
        spell_info = get_spells_for_class_spec(class_spec)
        if not spell_info:
            print(f"Error: No spell icons found for {class_spec}. Exiting...")
            return
        
        # Apply existing keybindings
        for spell_name, key in config["keybindings"].items():
            if spell_name in spell_info:
                spell_info[spell_name]["key"] = key
        
        print("\nLoaded keybindings:")
        for spell_name, info in spell_info.items():
            if "key" in info and info["key"]:
                print(f"  {spell_name}: {info['key']}")
        
        # Ask if user wants to edit any keybindings
        while True:
            edit = input("\nWould you like to edit any keybindings? (y/n): ")
            if edit.lower() == 'y':
                spell_info = configure_keybindings(spell_info)
                # Update config with new keybindings
                config["keybindings"] = {spell: info["key"] for spell, info in spell_info.items() if "key" in info and info["key"]}
                save_config(config)
                print("Configuration updated with new keybindings.")
                break
            elif edit.lower() == 'n':
                break
            else:
                print("Invalid input. Please enter 'y' or 'n'.")
                
        # Ask if user wants to reselect the screen region
        while True:
            edit_region = input("\nWould you like to reselect the screen region? (y/n): ")
            if edit_region.lower() == 'y':
                new_box_position = select_screen_region()
                if new_box_position:
                    box_position = new_box_position
                    config["location"] = [box_position[0], box_position[1]]
                    save_config(config)
                    print("Screen region updated.")
                break
            elif edit_region.lower() == 'n':
                break
            else:
                print("Invalid input. Please enter 'y' or 'n'.")
    else:
        # Go through full setup process
        print("\n=== SETUP ===")
        
        # Step 1: Select screen region for Hekili spellbox
        print("\nStep 1: Select the Hekili spellbox on your screen")
        box_position = select_screen_region()
        if not box_position:
            print("Screen region selection canceled. Exiting...")
            return
        config["location"] = [box_position[0], box_position[1]]
        
        # Step 2: Select class and spec
        print("\nStep 2: Select your class and specialization")
        class_spec = select_class_and_spec()
        config["Class"] = class_spec
        
        # Step 3: Get spell information and configure keybindings
        print("\nStep 3: Configure keybindings")
        spell_info = get_spells_for_class_spec(class_spec)
        if not spell_info:
            print(f"No spell icons found for {class_spec}. Exiting...")
            return
        
        # Check if we already have keybindings for this class/spec in config
        if "keybindings" in config and config["Class"] == class_spec:
            print("\nExisting keybindings found. Applying them...")
            for spell_name, key in config["keybindings"].items():
                if spell_name in spell_info:
                    spell_info[spell_name]["key"] = key
                    print(f"  Applied: {spell_name} -> {key}")
            
            # Ask if user wants to use these or reconfigure
            while True:
                use_existing = input("\nUse these existing keybindings? (y/n): ")
                if use_existing.lower() == 'y':
                    break
                elif use_existing.lower() == 'n':
                    spell_info = configure_keybindings(spell_info)
                    break
                else:
                    print("Invalid input. Please enter 'y' or 'n'.")
        else:
            spell_info = configure_keybindings(spell_info)
        
        config["keybindings"] = {spell: info["key"] for spell, info in spell_info.items() if "key" in info and info["key"]}
        
        # Save configuration
        save_config(config)
        print("\nConfiguration saved successfully!")
    
    # Step 4: Test recognition for problem spells
    print("\nStep 4: Test recognition for problem spells")
    while True:
        test_recognition = input("Would you like to test recognition for problematic spells? (y/n): ")
        if test_recognition.lower() == 'y':
            test_spell_recognition(spell_info, box_position)
            break
        elif test_recognition.lower() == 'n':
            break
        else:
            print("Invalid input. Please enter 'y' or 'n'.")
    
    # Start automation
    print("\n=== RUNNING ===")
    print("Automation will now start.")
    print("Press F3 to toggle automation on/off.")
    print("Press Ctrl+C to exit the program.")
    
    # Debug info for problematic spells
    problem_spells = ["storm_elemental", "ascendance"]
    found_problems = False
    for problem in problem_spells:
        for spell_name, info in spell_info.items():
            if problem.lower() in spell_name.lower():
                found_problems = True
                print(f"Special handling for: {spell_name} (Keybind: {info['key']})")
    
    if not found_problems:
        print("Warning: No problem spells (Storm Elemental/Ascendance) found in current configuration.")
    
    stop_event = threading.Event()
    automation_thread = threading.Thread(
        target=capture_and_compare,
        args=(box_position, spell_info, stop_event)
    )
    automation_thread.daemon = True
    automation_thread.start()
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting Auto_Hekili...")
        stop_event.set()
        automation_thread.join(timeout=3)

if __name__ == "__main__":
    main()