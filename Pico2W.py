import machine
import os
import time
import sdcard 

# --- 1. PIN CONFIGURATION (PICO 2 W OPTIMIZED) ---
# Moved to GP16-18 to avoid wireless chip interference
PUMP_IN1 = 16  
PUMP_IN2 = 17  
PUMP_ENA = 18  

# Fuel sender (ADC0)
LEVEL_ADC_PIN = 26 

# SD Card SPI pins (Switched to SPI1 for stability on "W" models)
SD_SPI_ID = 1    
SD_CS_PIN = 9    
SD_SPI_SCK = 10  
SD_SPI_MOSI = 11 
SD_SPI_MISO = 12 

# --- 2. LOGIC & CALIBRATION ---
PUMP_THRESHOLD_INCHES = 5.0
LOG_FILE_PATH = "/sd/water_log.txt"
LOOP_DELAY_SECONDS = 5 

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
    """Initialize all hardware components with Pico 2 W fixes."""
    global pump_in1, pump_in2, pump_ena, adc, sd
    
    print("--- System Initializing ---")
    
    # 1. Setup Pump Pins
    try:
        pump_in1 = machine.Pin(PUMP_IN1, machine.Pin.OUT)
        pump_in2 = machine.Pin(PUMP_IN2, machine.Pin.OUT)
        pump_ena = machine.PWM(machine.Pin(PUMP_ENA))
        pump_in1.value(0)
        pump_in2.value(0)
        pump_ena.duty_u16(0) 
        print(f"✅ Pump pins {PUMP_IN1}, {PUMP_IN2}, {PUMP_ENA} ready.")
    except Exception as e:
        print(f"❌ Pump Init Error: {e}")
        return False

    # 2. Setup ADC Pin
    try:
        adc = machine.ADC(machine.Pin(LEVEL_ADC_PIN))
        print(f"✅ ADC Pin {LEVEL_ADC_PIN} ready.")
    except Exception as e:
        print(f"❌ ADC Init Error: {e}")
        return False
        
    # 3. Setup and Mount SD Card
    try:
        # Step A: Pre-initialize CS pin
        cs = machine.Pin(SD_CS_PIN, machine.Pin.OUT)
        cs.value(1) # Ensure card is deselected initially
        
        # Step B: Clear any existing mounts to prevent "Device Busy" errors
        try:
            os.umount("/sd")
        except:
            pass
            
        # Step C: Initialize SPI1 at 400kHz (Safer for Pico 2 W)
        spi = machine.SPI(SD_SPI_ID,
                          baudrate=400000, 
                          polarity=0,
                          phase=0,
                          sck=machine.Pin(SD_SPI_SCK),
                          mosi=machine.Pin(SD_SPI_MOSI),
                          miso=machine.Pin(SD_SPI_MISO))
        
        # Step D: Mount
        sd = sdcard.SDCard(spi, cs)
        os.mount(sd, "/sd")
        print("✅ SD Card mounted successfully at /sd")
        
        # Write boot header
        log_to_sd("--- SYSTEM BOOT ---")
        return True
        
    except Exception as e:
        print(f"❌ SD Card Error: {e}")
        print("Check: Is sdcard.py on the Pico? Is card FAT32?")
        return False

def map_value(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def read_water_level():
    try:
        # Take 5 readings and average them to filter wireless noise
        readings = [adc.read_u16() for _ in range(5)]
        avg_adc = sum(readings) / len(readings)
        
        inches = map_value(avg_adc, ADC_EMPTY, ADC_FULL, LEVEL_EMPTY_INCHES, LEVEL_FULL_INCHES)
        # Clamp values between min/max
        return max(min(inches, LEVEL_FULL_INCHES), LEVEL_EMPTY_INCHES)
    except:
        return None

def log_to_sd(message):
    try:
        t = time.localtime()
        timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*t[0:6])
        with open(LOG_FILE_PATH, "a") as f:
            f.write(f"{timestamp}, {message}\n")
    except Exception as e:
        print(f"Logging error: {e}")

def control_pump(current_level):
    if current_level > PUMP_THRESHOLD_INCHES:
        pump_in1.value(1)
        pump_in2.value(0)
        pump_ena.duty_u16(65535) # Full Speed
        return "PUMPING"
    else:
        pump_ena.duty_u16(0)
        pump_in1.value(0)
        pump_in2.value(0)
        return "IDLE"
        
# --- 5. MAIN LOOP ---
def main():
    if not setup():
        print("Aborting: Hardware setup failed.")
        return 

    print("\nStarting Monitoring Loop... (Press Ctrl+C to stop)")
    
    while True:
        try:
            level = read_water_level()
            
            if level is not None:
                status = control_pump(level)
                output = f"Level: {level:.2f} in | Status: {status}"
                print(output)
                log_to_sd(output)
                
            time.sleep(LOOP_DELAY_SECONDS)
            
        except KeyboardInterrupt:
            print("\nStopping system...")
            break
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(2) 

    # --- Cleanup ---
    if pump_ena:
        pump_ena.duty_u16(0)
    try:
        os.umount("/sd")
        print("SD Card unmounted.")
    except:
        pass
    print("Cleanup complete. Goodbye.")

if __name__ == "__main__":
    main()
