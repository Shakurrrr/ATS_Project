from picamera2 import Picamera2
import cv2
import numpy as np
from pyzbar import pyzbar
import webbrowser
import RPi.GPIO as GPIO
import time
from RPLCD.i2c import CharLCD

# === Setup GPIO ===
LED_PIN = 27
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

# === Setup LCD ===
lcd = CharLCD('PCF8574', 0x27)  # Replace 0x27 with your I2C address if different
lcd.clear()

# === LED Blink Function ===
def blink_led(times=5, total_duration=10):
    interval = total_duration / (times * 2)
    for _ in range(times):
        GPIO.output(LED_PIN, GPIO.HIGH)
        time.sleep(interval)
        GPIO.output(LED_PIN, GPIO.LOW)
        time.sleep(interval)

# === Main QR Scanner ===
def scan_qr_code():
    picam2 = Picamera2()
    picam2.preview_configuration.main.size = (640, 480)
    picam2.preview_configuration.main.format = "RGB888"
    picam2.configure("preview")
    picam2.start()

    opened_urls = set()

    while True:
        frame = picam2.capture_array()
        decoded_objects = pyzbar.decode(frame)

        for obj in decoded_objects:
            data = obj.data.decode("utf-8")
            points = obj.polygon
            if points:
                pts = np.array([[p.x, p.y] for p in points], np.int32)
                pts = pts.reshape((-1, 1, 2))
                cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
                cv2.putText(frame, data, (pts[0][0][0], pts[0][0][1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

                if data.startswith("http") and data not in opened_urls:
                    webbrowser.open(data)
                    opened_urls.add(data)

                    # Blink LED and update LCD
                    blink_led()
                    lcd.clear()
                    lcd.write_string("QR Scanned!")

        cv2.imshow("QR Code Scanner", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    picam2.stop()
    cv2.destroyAllWindows()
    GPIO.cleanup()
    lcd.clear()

if __name__ == "__main__":
    try:
        scan_qr_code()
    except KeyboardInterrupt:
        GPIO.cleanup()
        lcd.clear()
        print("Stopped by user")
