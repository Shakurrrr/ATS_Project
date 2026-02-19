import time
from RPLCD.i2c import CharLCD

# Initialize LCD
lcd = CharLCD('PCF8574', 0x27)

# Example message to scroll
message = "Welcome SADIQ SURAJ... I am surprised you came early today!"

# How many characters the LCD can display (16 for 16x2)
width = 16

try:
    while True:
        for i in range(len(message) - width + 1):
            lcd.clear()
            lcd.write_string(message[i:i+width])
            time.sleep(0.3)
        # Pause at the end
        time.sleep(1)
except KeyboardInterrupt:
    lcd.clear()
    print("Scrolling stopped")
