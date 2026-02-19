import RPi.GPIO as GPIO
import time

# GPIO Pins
green_led_pin = 27
red_led_pin = 17

checkin_button_pin = 22
checkout_button_pin = 23

# Setup
GPIO.setmode(GPIO.BCM)

# LEDs as output
GPIO.setup(green_led_pin, GPIO.OUT)
GPIO.setup(red_led_pin, GPIO.OUT)

# Set both LEDs OFF at start
GPIO.output(green_led_pin, GPIO.LOW)
GPIO.output(red_led_pin, GPIO.LOW)

# Buttons as input with internal pull-up
GPIO.setup(checkin_button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(checkout_button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def blink_led(pin, duration=5, interval=0.5):
    end_time = time.time() + duration
    while time.time() < end_time:
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(interval)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(interval)

try:
    while True:
        if GPIO.input(checkin_button_pin) == GPIO.LOW:
            print("Check-in button pressed - Green LED BLINKING")
            blink_led(green_led_pin)
            # Make sure both LEDs OFF after blink
            GPIO.output(green_led_pin, GPIO.LOW)
            GPIO.output(red_led_pin, GPIO.LOW)
            time.sleep(0.3)  # debounce delay

        elif GPIO.input(checkout_button_pin) == GPIO.LOW:
            print("Check-out button pressed - Red LED BLINKING")
            blink_led(red_led_pin)
            GPIO.output(green_led_pin, GPIO.LOW)
            GPIO.output(red_led_pin, GPIO.LOW)
            time.sleep(0.3)

        else:
            # Always force both LEDs OFF when no button pressed
            GPIO.output(green_led_pin, GPIO.LOW)
            GPIO.output(red_led_pin, GPIO.LOW)

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Exiting program")

finally:
    GPIO.cleanup()
