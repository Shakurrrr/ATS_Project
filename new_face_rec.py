import RPi.GPIO as GPIO
import face_recognition
import cv2
import numpy as np
import qrcode
import pandas as pd
from datetime import datetime, timedelta
from pyzbar.pyzbar import decode
import os
import pickle
import time
from picamera2 import Picamera2
from RPLCD.i2c import CharLCD
import hashlib
import smtplib
from email.message import EmailMessage

# Constants and File Paths
BASE_DIR = "/home/pi/Desktop/PROJECT/EMSAT_EMPLOYEE/ATS_PROJECT"
EMP_DIR = os.path.join(BASE_DIR, "employees")                 # employees/<First_Last>/photo_files
ENCODINGS_FILE = os.path.join(EMP_DIR, "encodings.pickle")    # cache of encodings
ATTEND_DIR = os.path.join(BASE_DIR, "attendance")             # daily CSVs
REPORTS_DIR = os.path.join(BASE_DIR, "reports")




# GPIO & LCD Setup
PIR_PIN = 17
LED_PIN = 27
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)

lcd = CharLCD('PCF8574', 0x27)

# Camera Setup
picam2 = Picamera2()
preview_config = picam2.create_preview_configuration()
picam2.configure(picam2.create_preview_configuration(main={"format": 'XRGB8888', "size": (640, 480)}))
picam2.start()

# Globals
cv_scaler = 2
face_locations = []
face_encodings = []
face_names = []
recent_attendance = {}
attendance_count = 0


def process_frame(frame):
    global face_locations, face_encodings, face_names
    resized_frame = cv2.resize(frame, (0, 0), fx=1/cv_scaler, fy=1/cv_scaler)
    rgb_resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_resized_frame)
    face_encodings = face_recognition.face_encodings(rgb_resized_frame, face_locations, model='large')
    face_names = []
    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"
        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        if len(face_distances) > 0:
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_face_names[best_match_index]
        face_names.append(name)
    return frame

def draw_results(frame):
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        top *= cv_scaler
        right *= cv_scaler
        bottom *= cv_scaler
        left *= cv_scaler
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.rectangle(frame, (left - 3, top - 35), (right + 3, top), (0, 255, 0), cv2.FILLED)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, name, (left + 6, top - 6), font, 1.0, (255, 255, 255), 1)
    return frame

def generate_qr(student_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expiration = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    token_string = f"{student_id}|{CLASS_SESSION_ID}|{SECRET_KEY}"
    token_hash = hashlib.sha256(token_string.encode()).hexdigest()
    qr_data = f"{student_id}|{timestamp}|{expiration}|{token_hash}"
    img = qrcode.make(qr_data)
    os.makedirs(QR_DIR, exist_ok=True)
    qr_path = os.path.join(QR_DIR, f"{student_id}.png")
    img.save(qr_path)
    return qr_path, timestamp, expiration, token_hash

def send_qr_email(email_to, image_path):
    try:
        msg = EmailMessage()
        msg['Subject'] = 'Your Attendance QR Code'
        msg['From'] = SENDER_EMAIL
        msg['To'] = email_to
        msg.set_content('Scan the attached QR code within 15 minutes of class start.')
        with open(image_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='image', subtype='png', filename='qr.png')
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
        print(f"[EMAIL] Sent to {email_to}")
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send to {email_to}: {e}")

def log_attendance(row, timestamp):
    global attendance_count, attendance_df
    record = {
        "Name": row["Name"],
        "StudentID": row["StudentID"],
        "Email": row["Email"],
        "ClassSession": CLASS_SESSION_ID,
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Time": datetime.now().strftime("%H:%M"),
        "AttendanceTime": timestamp,
        "Status": "Present"
    }
    attendance_df = pd.concat([attendance_df, pd.DataFrame([record])], ignore_index=True)
    attendance_count += 1
    # Uncomment the below lines to save after every log (optional, may cause slowdowns)
    # save_attendance_files()

def save_attendance_files():
    global attendance_df
    attendance_df.to_excel(ATTENDANCE_FILE, index=False)
    session_df = attendance_df[(attendance_df["ClassSession"] == CLASS_SESSION_ID) & 
                               (attendance_df["Date"] == datetime.now().strftime("%Y-%m-%d"))]
    session_df.to_excel(SESSION_FILE, index=False)

def wait_for_motion():
    lcd.clear()
    lcd.write_string("Waiting for         student")
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
    expiration_dt = datetime.strptime(expiration, "%Y-%m-%d %H:%M:%S")
    while True:
        if datetime.now() > expiration_dt:
            lcd.clear()
            lcd.write_string("QR expired")
            cv2.destroyAllWindows()
            return False
        frame = picam2.capture_array()
        if frame is None:
            continue
        decoded_objects = decode(frame)
        for obj in decoded_objects:
            content = obj.data.decode('utf-8')
            parts = content.split("|")
            if len(parts) == 4 and expected_id == parts[0] and parts[3] == expected_hash:
                cv2.destroyAllWindows()
                return True
        cv2.imshow("Scan QR", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cv2.destroyAllWindows()
    return False

# FSM Initialization
lcd.clear()
lcd.write_string("System Init...        Wait 1 mins")
time.sleep(60)

lcd.clear()
lcd.write_string("Sending Emails...")
for _, row in students_df.iterrows():
    qr_path, _, _, _ = generate_qr(row["StudentID"])
    send_qr_email(row["Email"], qr_path)
lcd.clear()
lcd.write_string("Emails sent. Ready.")

# Main FSM Loop
try:
    while True:
        wait_for_motion()
        while True:
            frame = picam2.capture_array()
            frame = process_frame(frame)
            frame = draw_results(frame)
            cv2.imshow("Preview", frame)
            cv2.waitKey(1)
            if len(face_names) > 0 and face_names[0] != "Unknown":
                break
        name = face_names[0]
        if name in recent_attendance and (datetime.now() - recent_attendance[name]).total_seconds() < 900:
            lcd.clear()
            lcd.write_string("Duplicate scan      blocked")
            time.sleep(2)
            continue
        student_info = students_df.loc[students_df["Name"] == name]
        if student_info.empty:
            lcd.clear()
            lcd.write_string("Student not\nfound")
            time.sleep(2)
            continue
        student = student_info.iloc[0]
        qr_path, timestamp, expiration, hash_token = generate_qr(student["StudentID"])
        lcd.clear()
        lcd.write_string(f"{name[:16]}\nScan QR now...")
        if scan_qr(student["StudentID"], expiration, hash_token):
            log_attendance(student, timestamp)
            lcd.clear()
            lcd.write_string(f"{name[:16]}\nPresent: {attendance_count}")
            time.sleep(1)
            lcd.clear()
            lcd.write_string("Attendance logged")
            for _ in range(attendance_count):
                GPIO.output(LED_PIN, GPIO.HIGH)
                time.sleep(0.3)
                GPIO.output(LED_PIN, GPIO.LOW)
                time.sleep(0.2)
            recent_attendance[name] = datetime.now()
            time.sleep(2)

except KeyboardInterrupt:
    # Save attendance files on exit
    save_attendance_files()
    lcd.clear()
    GPIO.cleanup()
    picam2.stop()
    cv2.destroyAllWindows()
    print("[SYSTEM] Shutdown complete.")
