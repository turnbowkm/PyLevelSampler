import machine
import os
import time
import sdcard # Ensure this file is on your Pico

# --- 1. PIN CONFIGURATION (PICO-SPECIFIC PINS) ---
# L298N Motor Driver Pins
PUMP_IN1 = 15  # Direction Pin 1 (PWM capable)
PUMP_IN2 = 14  # Direction Pin 2 (PWM capable)
PUMP_ENA = 13  # Enable/Speed Pin (PWM capable)

# Fuel sender (water level) connected to an ADC pin
LEVEL_ADC_PIN = 26 # Pico standard ADC0 pin

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

# Calibrated ADC values (Must be determined experimentally!)
ADC_EMPTY = 11000  
ADC_FULL = 48000   
LEVEL_EMPTY_INCHES = 0.0
LEVEL_FULL_INCHES = 10.0 

# --- 3. GLOBAL OBJECTS ---
pump_in1 = None
pump_in2 = None
pump_ena = None
adc = None
sd = None

# --- 4. HELPER FUNCTIONS ---

def setup():
    """Initialize all hardware components."""
    global pump_in1, pump_in2, pump_ena, adc, sd
    
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

    # 2. Setup ADC Pin
    try:
        adc = machine.ADC(machine.Pin(LEVEL_ADC_PIN))
        print(f"✅ ADC pin {LEVEL_ADC_PIN} initialized.")
    except Exception as e:
        print(f"❌ Error initializing ADC pin: {e}")
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

# --- Mapping and Logging functions (Unchanged from previous full script) ---

def map_value(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def read_water_level():
    try:
        raw_adc = adc.read_u16() 
        inches = map_value(raw_adc, ADC_EMPTY, ADC_FULL, LEVEL_EMPTY_INCHES, LEVEL_FULL_INCHES)
        if inches < LEVEL_EMPTY_INCHES: inches = LEVEL_EMPTY_INCHES
        if inches > LEVEL_FULL_INCHES: inches = LEVEL_FULL_INCHES
        return inches
    except:
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
    if current_level > PUMP_THRESHOLD_INCHES:
        # Turn ON
        pump_in1.value(1)
        pump_in2.value(0)
        pump_ena.duty_u16(65535)
        print("Status: PUMPING")
    else:
        # FORCE OFF - If level is 0, this WILL execute
        pump_ena.duty_u16(0)
        pump_in1.value(0)
        pump_in2.value(0)
        print("Status: STOPPED")
        
# --- 5. MAIN LOOP ---
def main():
    if not setup():
        print("System Halted.")
        return 

    print("\nStarting monitoring loop...")
    
    while True:
        try:
            level_inches = read_water_level()
            
            if level_inches is not None:
                print(f"[{time.time()}] Current Level: {level_inches:.2f} inches")
                log_to_sd(f"Level: {level_inches:.2f} in")
                control_pump(level_inches)
                
            time.sleep(LOOP_DELAY_SECONDS)
            
        except KeyboardInterrupt:
            print("\nLoop stopped by user.")
            break
        except Exception as e:
            print(f"\nMain loop error: {e}")
            log_to_sd(f"FATAL ERROR: {e}")
            time.sleep(5) 

    # --- Cleanup ---
    if pump_ena:
        pump_ena.duty_u16(0)
        pump_in1.value(0)
        pump_in2.value(0)
        print("Pump is safely turned OFF.")
    if sd:
        try:
            os.umount("/sd")
            print("SD Card unmounted.")
        except:
            print("Could not unmount SD card.")

if __name__ == "__main__":
    main()
