import os
import sys
import RPi.GPIO as GPIO
import face_recognition
import cv2
import numpy as np
import qrcode
import pandas as pd
from datetime import datetime, timedelta
from pyzbar.pyzbar import decode
import pickle
import time
from picamera2 import Picamera2
from RPLCD.i2c import CharLCD
import hashlib
import smtplib
from email.message import EmailMessage

# === DISPLAY ENV FIX ===
os.environ["DISPLAY"] = ":0"

# === Constants and File Paths ===
BASE_DIR = "/home/pi/Desktop/PROJECT/N-facial-recognition-QRCODE"
QR_DIR = os.path.join(BASE_DIR, "QR-CODE")
ATTENDANCE_FILE = os.path.join(BASE_DIR, "attendance_log.xlsx")
STUDENT_FILE = os.path.join(BASE_DIR, "student_list.xlsx")
ENCODINGS_FILE = os.path.join(BASE_DIR, "encodings.pickle")
CLASS_SESSION_ID = "CS101_2025_05_23"
SESSION_FILE = os.path.join(BASE_DIR, f"attendance_{CLASS_SESSION_ID}_{datetime.now().strftime('%Y-%m-%d')}.xlsx")

# === Email Config ===
SECRET_KEY = "ATS1590"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "Yusufelpercy@gmail.com"
SMTP_PASSWORD = "wtru qgtj lzoz eunp"  # App password
SENDER_EMAIL = SMTP_USERNAME

# === Load student data and encodings ===
students_df = pd.read_excel(STUDENT_FILE)
with open(ENCODINGS_FILE, "rb") as f:
    data = pickle.load(f)

known_face_encodings = data["encodings"]
known_face_names = data["names"]

# === GPIO & LCD Setup ===
PIR_PIN = 17
LED_PIN = 27
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)
lcd = CharLCD('PCF8574', 0x27)

# === Camera Setup ===
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(main={"format": 'XRGB8888', "size": (640, 480)}))
picam2.start()

# === Globals ===
cv_scaler = 2
face_locations = []
face_encodings = []
face_names = []
recent_attendance = {}
attendance_count = 0

try:
    attendance_df = pd.read_excel(ATTENDANCE_FILE)
except FileNotFoundError:
    attendance_df = pd.DataFrame(columns=["Name", "StudentID", "Email", "ClassSession", "Date", "Time", "AttendanceTime", "Status"])

# === Functions ===
def process_frame(frame):
    global face_locations, face_encodings, face_names
    resized_frame = cv2.resize(frame, (0, 0), fx=1/cv_scaler, fy=1/cv_scaler)
    rgb_resized = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_resized)
    face_encodings = face_recognition.face_encodings(rgb_resized, face_locations)
    face_names = []

    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"
        if matches:
            best_match = np.argmin(face_recognition.face_distance(known_face_encodings, face_encoding))
            if matches[best_match]:
                name = known_face_names[best_match]
        face_names.append(name)
    return frame

def draw_results(frame):
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        top *= cv_scaler; right *= cv_scaler; bottom *= cv_scaler; left *= cv_scaler
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(frame, name, (left + 6, top - 6), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 1)
    return frame

def generate_qr(student_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expiration = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    token = hashlib.sha256(f"{student_id}|{CLASS_SESSION_ID}|{SECRET_KEY}".encode()).hexdigest()
    qr_data = f"{student_id}|{timestamp}|{expiration}|{token}"
    qr_img = qrcode.make(qr_data)
    os.makedirs(QR_DIR, exist_ok=True)
    path = os.path.join(QR_DIR, f"{student_id}.png")
    qr_img.save(path)
    return path, timestamp, expiration, token

def send_qr_email(to_email, image_path):
    msg = EmailMessage()
    msg['Subject'] = 'Your Attendance QR Code'
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg.set_content('Scan the QR code within 15 minutes.')

    with open(image_path, 'rb') as f:
        msg.add_attachment(f.read(), maintype='image', subtype='png', filename='qr.png')

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(msg)

def log_attendance(row, timestamp):
    global attendance_df, attendance_count
    attendance_df = pd.concat([attendance_df, pd.DataFrame([{
        "Name": row["Name"],
        "StudentID": row["StudentID"],
        "Email": row["Email"],
        "ClassSession": CLASS_SESSION_ID,
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Time": datetime.now().strftime("%H:%M"),
        "AttendanceTime": timestamp,
        "Status": "Present"
    }])], ignore_index=True)
    attendance_count += 1

def save_attendance_files():
    attendance_df.to_excel(ATTENDANCE_FILE, index=False)
    session_df = attendance_df[
        (attendance_df["ClassSession"] == CLASS_SESSION_ID) &
        (attendance_df["Date"] == datetime.now().strftime("%Y-%m-%d"))
    ]
    session_df.to_excel(SESSION_FILE, index=False)

def wait_for_motion():
    lcd.clear()
    lcd.write_string("Waiting for student")
    while not GPIO.input(PIR_PIN):
        time.sleep(0.5)
    lcd.clear()
    lcd.write_string("Motion detected")
    time.sleep(1)
    lcd.clear()
    lcd.write_string("Looking for face...")

def scan_qr(expected_id, expiration, expected_hash):
    lcd.clear()
    lcd.write_string("Scan QR code...")
    exp_time = datetime.strptime(expiration, "%Y-%m-%d %H:%M:%S")
    while True:
        if datetime.now() > exp_time:
            lcd.clear(); lcd.write_string("QR expired")
            cv2.destroyAllWindows()
            return False
        frame = picam2.capture_array()
        decoded = decode(frame)
        for obj in decoded:
            data = obj.data.decode('utf-8').split("|")
            if len(data) == 4 and data[0] == expected_id and data[3] == expected_hash:
                cv2.destroyAllWindows()
                return True
        cv2.imshow("Scan QR", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cv2.destroyAllWindows()
    return False

# === FSM Start ===
lcd.clear()
lcd.write_string("System Init...Wait")
time.sleep(10)

# Send QR emails
lcd.clear()
lcd.write_string("Sending Emails...")
email_success = True
for _, row in students_df.iterrows():
    try:
        path, _, _, _ = generate_qr(row["StudentID"])
        send_qr_email(row["Email"], path)
    except Exception as e:
        lcd.clear(); lcd.write_string("Email failed")
        print(f"[EMAIL ERROR] {e}")
        email_success = False
        break

if not email_success:
    GPIO.cleanup()
    picam2.stop()
    sys.exit()

lcd.clear()
lcd.write_string("Emails sent. Ready.")

try:
    while True:
        wait_for_motion()
        while True:
            frame = picam2.capture_array()
            processed = process_frame(frame)
            output = draw_results(processed)
            cv2.imshow("Preview", output)
            cv2.waitKey(1)
            if face_names and face_names[0] != "Unknown":
                break

        name = face_names[0]
        if name in recent_attendance and (datetime.now() - recent_attendance[name]).total_seconds() < 900:
            lcd.clear(); lcd.write_string("Duplicate Blocked")
            time.sleep(2)
            continue

        student_info = students_df[students_df["Name"] == name]
        if student_info.empty:
            lcd.clear(); lcd.write_string("Student not found")
            time.sleep(2)
            continue

        student = student_info.iloc[0]
        path, timestamp, expiration, token = generate_qr(student["StudentID"])
        lcd.clear(); lcd.write_string(f"{name[:16]}\nScan QR now...")
        if scan_qr(student["StudentID"], expiration, token):
            log_attendance(student, timestamp)
            lcd.clear(); lcd.write_string(f"{name[:16]}\nLogged: {attendance_count}")
            for _ in range(attendance_count):
                GPIO.output(LED_PIN, GPIO.HIGH)
                time.sleep(0.2)
                GPIO.output(LED_PIN, GPIO.LOW)
                time.sleep(0.1)
            recent_attendance[name] = datetime.now()
            time.sleep(2)

except KeyboardInterrupt:
    save_attendance_files()
    lcd.clear()
    GPIO.cleanup()
    picam2.stop()
    cv2.destroyAllWindows()
    print("[SYSTEM] Shutdown complete.")
