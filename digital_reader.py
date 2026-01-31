import subprocess
import re
import cv2
import time
import os
from gauge_logic import GaugeReader  # Assumes you saved the class in gauge_logic.py

# --- Configuration ---
TARGET_LABEL = "staff_gauge"  # Change this to match your model's label
CSV_FILE = "water_levels.csv"
SNAPSHOT_PATH = "current_gauge.jpg"

# Initialize our specialized gauge tool
gauge_tool = GaugeReader()

# The command to run the Hailo-8 inference
CMD = [
    "rpicam-hello",
    "-t", "0",
    "--post-process-file", "/usr/share/rpi-camera-assets/hailo_yolov6_inference.json",
    "--verbose", "2"
]

# Regex to capture the Hailo output
pattern = re.compile(r"Object:\s+(\w+)\[\d+\]\s+\(([\d.]+)\)\s+@\s+(\d+),(\d+)\s+(\d+)x(\d+)")

print(f"--- Starting Stream: Monitoring for {TARGET_LABEL} ---")

# Start the camera process
process = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

try:
    while True:
        line = process.stderr.readline()
        if not line:
            continue

        match = pattern.search(line)
        if match:
            label, conf, x, y, w, h = match.groups()
            conf = float(conf)

            # Only trigger if we find our gauge and confidence is high
            if label.lower() == TARGET_LABEL and conf > 0.3:
                print(f"[{time.strftime('%H:%M:%S')}] Gauge detected ({conf:.2f}). Calculating level...")
                
                # 1. Capture a high-quality still for the OCR
                # -n flag prevents a preview window from popping up
                subprocess.run(["rpicam-still", "-o", SNAPSHOT_PATH, "-t", "500", "-n"])
                
                full_img = cv2.imread(SNAPSHOT_PATH)
                if full_img is None:
                    continue

                # 2. Flatten, Find Line, and Read Numbers
                try:
                    # Convert regex strings to integers
                    ix, iy, iw, ih = int(x), int(y), int(w), int(h)
                    
                    warped = gauge_tool.get_warped_gauge(full_img, ix, iy, iw, ih)
                    water_y = gauge_tool.find_water_line(warped)
                    level, ref_num = gauge_tool.read_level(warped, water_y)

                    if level is not None:
                        print(f"✅ SUCCESS: Water Level at {level} (Ref: {ref_num})")
                        
                        # 3. Log to CSV
                        with open(CSV_FILE, "a") as f:
                            f.write(f"{time.time()},{level},{ref_num}\n")
                        
                        # 4. Save a debug image so you can see the line detection
                        cv2.line(warped, (0, water_y), (150, water_y), (0, 255, 0), 2)
                        cv2.imwrite("last_detection_debug.jpg", warped)
                    else:
                        print("⚠️ Gauge found, but could not read numbers.")

                except Exception as e:
                    print(f"Processing error: {e}")

                # Wait a bit so we don't spam the CPU/logs
                time.sleep(10) 

except KeyboardInterrupt:
    print("\nStopping monitor...")
finally:
    process.terminate()