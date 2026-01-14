import machine
import os
import time
import sdcard # Ensure this file is on your Pico

# --- 1. PIN CONFIGURATION (PICO-SPECIFIC PINS) ---
# L298N Motor Driver Pins
PUMP_IN1 = 15  # Direction Pin 1 (PWM capable)
PUMP_IN2 = 14  # Direction Pin 2 (PWM capable)
PUMP_ENA = 13  # Enable/Speed Pin (PWM capable)

# TF Luna LiDAR UART pins
LIDAR_UART_ID = 1  # Using UART1
LIDAR_TX_PIN = 8   # Pico TX (connects to LiDAR RX)
LIDAR_RX_PIN = 9   # Pico RX (connects to LiDAR TX)
LIDAR_BAUDRATE = 115200  # TF Luna default baudrate

# SD Card SPI pins (using SPI0 standard assignment)
SD_SPI_ID = 0    # Using SPI peripheral 0
SD_CS_PIN = 5    # Chip Select (CS) can be any GPIO
SD_SPI_SCK = 2   # Serial Clock (SCK)
SD_SPI_MOSI = 3  # Master Out Slave In (MOSI)
SD_SPI_MISO = 4  # Master In Slave Out (MISO)

# --- 2. LOGIC & CALIBRATION (FILL THESE IN!) ---
PUMP_THRESHOLD_INCHES = 5.0
LOG_FILE_PATH = "/sd/water_log.txt"
LOOP_DELAY_SECONDS = 5 

# Calibrated distance values (Must be determined experimentally!)
# Distance from sensor to EMPTY tank bottom (in cm)
DISTANCE_EMPTY_CM = 100.0  # Example: sensor 100cm from empty tank bottom
# Distance from sensor to FULL tank (in cm)
DISTANCE_FULL_CM = 20.0    # Example: sensor 20cm from full water level
# Tank depth in inches
LEVEL_EMPTY_INCHES = 0.0
LEVEL_FULL_INCHES = 10.0 

# --- 3. GLOBAL OBJECTS ---
pump_in1 = None
pump_in2 = None
pump_ena = None
lidar_uart = None
sd = None

# --- 4. HELPER FUNCTIONS ---

def setup():
    """Initialize all hardware components."""
    global pump_in1, pump_in2, pump_ena, lidar_uart, sd
    
    # 1. Setup Pump Pins
    try:
        pump_in1 = machine.Pin(PUMP_IN1, machine.Pin.OUT)
        pump_in2 = machine.Pin(PUMP_IN2, machine.Pin.OUT)
        pump_ena = machine.PWM(machine.Pin(PUMP_ENA))
        pump_in1.value(0)
        pump_in2.value(0)
        pump_ena.duty_u16(0) 
        print("✅ L298N Pump pins initialized (OFF).")
    except Exception as e:
        print(f"❌ Error initializing pump pins: {e}")
        return False

    # 2. Setup TF Luna LiDAR UART
    try:
        lidar_uart = machine.UART(LIDAR_UART_ID, 
                                  baudrate=LIDAR_BAUDRATE,
                                  tx=machine.Pin(LIDAR_TX_PIN),
                                  rx=machine.Pin(LIDAR_RX_PIN),
                                  bits=8,
                                  parity=None,
                                  stop=1)
        print(f"✅ TF Luna LiDAR UART{LIDAR_UART_ID} initialized on pins TX:{LIDAR_TX_PIN}, RX:{LIDAR_RX_PIN}")
    except Exception as e:
        print(f"❌ Error initializing LiDAR UART: {e}")
        return False
        
    # 3. Setup and Mount SD Card (PICO SPI PINS USED)
    try:
        # Initialize SPI with corrected pins
        spi = machine.SPI(SD_SPI_ID,
                          baudrate=1000000,
                          polarity=0,
                          phase=0,
                          sck=machine.Pin(SD_SPI_SCK),
                          mosi=machine.Pin(SD_SPI_MOSI),
                          miso=machine.Pin(SD_SPI_MISO))
        
        cs = machine.Pin(SD_CS_PIN, machine.Pin.OUT)
        sd = sdcard.SDCard(spi, cs)
        
        os.mount(sd, "/sd")
        print("✅ SD Card mounted successfully at /sd")
        log_to_sd("--- System Boot ---")
        return True
        
    except OSError as e:
        print(f"❌ SD Card Error. Check wiring or formatting (FAT32?). {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to initialize SD card: {e}")
        return False

def map_value(x, in_min, in_max, out_min, out_max):
    """Map a value from one range to another."""
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def read_tf_luna():
    """
    Read distance from TF Luna LiDAR sensor.
    TF Luna standard data format: 9 bytes per frame
    [0x59, 0x59, Dist_L, Dist_H, Strength_L, Strength_H, Temp_L, Temp_H, Checksum]
    Returns distance in cm or None if read fails.
    """
    try:
        if lidar_uart.any() >= 9:
            # Read available data
            data = lidar_uart.read(9)
            
            # Check for valid frame header (0x59 0x59)
            if data[0] == 0x59 and data[1] == 0x59:
                # Calculate checksum
                checksum = sum(data[0:8]) & 0xFF
                
                if checksum == data[8]:
                    # Extract distance (low byte + high byte)
                    distance_cm = data[2] + (data[3] << 8)
                    return distance_cm
                else:
                    print("⚠️ LiDAR checksum error")
                    return None
            else:
                # Clear buffer if header is invalid
                lidar_uart.read()
                return None
        else:
            return None
            
    except Exception as e:
        print(f"❌ Error reading TF Luna: {e}")
        return None

def read_water_level():
    """
    Read water level using TF Luna LiDAR.
    Converts distance measurement to water level in inches.
    Note: LiDAR measures distance TO water surface, so:
    - Greater distance = less water (empty)
    - Shorter distance = more water (full)
    """
    try:
        distance_cm = read_tf_luna()
        
        if distance_cm is None:
            return None
        
        # Convert distance to water level
        # The farther the distance, the lower the water level
        inches = map_value(distance_cm, 
                          DISTANCE_FULL_CM, DISTANCE_EMPTY_CM,  # Note: reversed
                          LEVEL_FULL_INCHES, LEVEL_EMPTY_INCHES)
        
        # Clamp to valid range
        if inches < LEVEL_EMPTY_INCHES: 
            inches = LEVEL_EMPTY_INCHES
        if inches > LEVEL_FULL_INCHES: 
            inches = LEVEL_FULL_INCHES
            
        return inches
        
    except Exception as e:
        print(f"❌ Error calculating water level: {e}")
        return None

def log_to_sd(message):
    """Appends a timestamped message to the log file."""
    try:
        t = time.localtime()
        timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5])
        log_entry = f"{timestamp}, {message}\n"
        with open(LOG_FILE_PATH, "a") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Error writing to SD card: {e}")

def control_pump(current_level):
    """Control pump based on water level threshold."""
    if current_level > PUMP_THRESHOLD_INCHES:
        # Turn ON
        pump_in1.value(1)
        pump_in2.value(0)
        pump_ena.duty_u16(65535)
        print("Status: PUMPING")
    else:
        # FORCE OFF - If level is at or below threshold
        pump_ena.duty_u16(0)
        pump_in1.value(0)
        pump_in2.value(0)
        print("Status: STOPPED")
        
# --- 5. MAIN LOOP ---
def main():
    if not setup():
        print("System Halted.")
        return 

    print("\n🚀 Starting water level monitoring with TF Luna LiDAR...")
    print(f"📊 Pump threshold: {PUMP_THRESHOLD_INCHES} inches")
    print(f"📏 LiDAR calibration: Empty={DISTANCE_EMPTY_CM}cm, Full={DISTANCE_FULL_CM}cm\n")
    
    while True:
        try:
            level_inches = read_water_level()
            
            if level_inches is not None:
                print(f"[{time.time()}] Current Level: {level_inches:.2f} inches")
                log_to_sd(f"Level: {level_inches:.2f} in")
                control_pump(level_inches)
            else:
                print("⚠️ Failed to read water level from LiDAR")
                
            time.sleep(LOOP_DELAY_SECONDS)
            
        except KeyboardInterrupt:
            print("\n🛑 Loop stopped by user.")
            break
        except Exception as e:
            print(f"\n❌ Main loop error: {e}")
            log_to_sd(f"FATAL ERROR: {e}")
            time.sleep(5) 

    # --- Cleanup ---
    if pump_ena:
        pump_ena.duty_u16(0)
        pump_in1.value(0)
        pump_in2.value(0)
        print("✅ Pump is safely turned OFF.")
    if sd:
        try:
            os.umount("/sd")
            print("✅ SD Card unmounted.")
        except:
            print("⚠️ Could not unmount SD card.")

if __name__ == "__main__":
    main()
