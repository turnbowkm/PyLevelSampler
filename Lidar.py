# --- ADD THESE TO YOUR CALIBRATION SECTION ---
PUMP_HEIGHT_CM = 10.0  # Physical height where the pump sits
PRIME_DURATION_BASE = 2.0  # Minimum seconds to prime
PRIME_FACTOR = 0.5         # Extra seconds per inch of "lift"

# Add a global variable to track state
is_pumping = False

def prime_pump(p1, p2, en, lift_inches):
    """
    Runs the pump at full speed to clear air.
    Duration scales based on how far the water has to travel.
    """
    # Calculate duration: further water = longer prime
    duration = PRIME_DURATION_BASE + (lift_inches * PRIME_FACTOR)
    duration = min(duration, 10.0) # Cap at 10s for safety
    
    print(f"🌊 Priming: Lift is {lift_inches:.1f}in. Running for {duration:.1f}s...")
    
    p1.value(1)
    p2.value(0)
    en.duty_u16(65535) # Max Power
    time.sleep(duration)
    print("✅ Priming Complete.")

# --- MODIFIED MAIN LOOP LOGIC ---
def main():
    global is_pumping
    p1, p2, en, uart = setup_hardware()
    if not p1: return 

    while True:
        raw_cm = get_reading(uart)
        if raw_cm:
            inches = (raw_cm - FULL_CM) * (EMPTY_IN - FULL_IN) / (EMPTY_CM - FULL_CM) + FULL_IN
            inches = max(min(inches, FULL_IN), EMPTY_IN)
            
            # Distance from water to the pump (Lift)
            # Assuming raw_cm is distance from sensor (at top) to water
            # and pump is mounted somewhere in between.
            lift_cm = raw_cm - PUMP_HEIGHT_CM
            lift_inches = lift_cm * 0.3937 # Convert to inches
            
            # --- PRIMING & CONTROL LOGIC ---
            if inches > (PUMP_THRESHOLD + 0.2):
                if not is_pumping:
                    # We were OFF, now turning ON -> Trigger Prime
                    prime_pump(p1, p2, en, max(0, lift_inches))
                    is_pumping = True
                
                # Normal running speed (maybe 80% power to save the motor)
                p1.value(1); p2.value(0); en.duty_u16(50000) 
                
            elif inches < (PUMP_THRESHOLD - 0.2):
                p1.value(0); p2.value(0); en.duty_u16(0)
                is_pumping = False
            
            log_data(raw_cm, inches)
        else:
            p1.value(0); p2.value(0); en.duty_u16(0)
            is_pumping = False
            
        time.sleep(1)
