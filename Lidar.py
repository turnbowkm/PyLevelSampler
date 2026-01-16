import machine
import os
import time

# Attempt to import the SD Card driver
try:
    import sdcard
except ImportError:
    print("❌ ERROR: sdcard.py not found on Pico! Upload it via Thonny first.")

# --- PIN CONFIG ---
PUMP_IN1, PUMP_IN2, PUMP_ENA = 15, 14, 13
LIDAR_TX, LIDAR_RX = 8, 9
SD_CS, SD_SCK, SD_MOSI, SD_MISO = 5, 2, 3, 4

# --- CALIBRATION ---
PUMP_THRESHOLD = 5.0
EMPTY_CM, FULL_CM = 100.0, 20.0
EMPTY_IN, FULL_IN = 0.0, 10.0

# --- HARDWARE SETUP ---
def setup_hardware():
    try:
        # Pump
        p1 = machine.Pin(PUMP_IN1, machine.Pin.OUT)
        p2 = machine.Pin(PUMP_IN2, machine.Pin.OUT)
        en = machine.PWM(machine.Pin(PUMP_ENA))
        p1.value(0); p2.value(0); en.duty_u16(0)

        # LiDAR (UART1)
        uart = machine.UART(1, baudrate=115200, tx=machine.Pin(LIDAR_TX), rx=machine.Pin(LIDAR_RX))

        # SD Card (SPI0)
        spi = machine.SPI(0, baudrate=1000000, sck=machine.Pin(SD_SCK), mosi=machine.Pin(SD_MOSI), miso=machine.Pin(SD_MISO))
        cs = machine.Pin(SD_CS, machine.Pin.OUT)
        sd = sdcard.SDCard(spi, cs)
        vfs = os.VfsFat(sd)
        os.mount(vfs, "/sd")
        
        return p1, p2, en, uart
    except Exception as e:
        print(f"❌ Hardware Init Failed: {e}")
        return None, None, None, None

def get_reading(uart):
    # Clear old data
    while uart.any(): uart.read()
    
    # Wait for frame
    start = time.ticks_ms()
    while uart.any() < 9:
        if time.ticks_diff(time.ticks_ms(), start) > 500: return None
    
    data = uart.read(9)
    if data[0] == 0x59 and data[1] == 0x59:
        if (sum(data[:8]) & 0xFF) == data[8]:
            return data[2] + (data[3] << 8)
    return None

def main():
    p1, p2, en, uart = setup_hardware()
    if not p1: return # Stop if hardware fails

    print("🚀 System Running...")
    
    while True:
        raw_cm = get_reading(uart)
        if raw_cm:
            # Simple Map: (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
            inches = (raw_cm - FULL_CM) * (EMPTY_IN - FULL_IN) / (EMPTY_CM - FULL_CM) + FULL_IN
            inches = max(min(inches, FULL_IN), EMPTY_IN)
            
            # Pump Logic
            if inches > (PUMP_THRESHOLD + 0.5):
                p1.value(1); p2.value(0); en.duty_u16(65535)
            elif inches < (PUMP_THRESHOLD - 0.5):
                p1.value(0); p2.value(0); en.duty_u16(0)
                
            print(f"Level: {inches:.2f} in (Raw: {raw_cm} cm)")
        else:
            print("⚠️ LiDAR timeout")
            
        time.sleep(2)

if __name__ == "__main__":
    main()
