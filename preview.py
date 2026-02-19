import cv2
from picamera2 import Picamera2

# Initialize the camera
picam2 = Picamera2()

# Create a preview configuration and set up the camera
preview_config = picam2.create_preview_configuration()
picam2.configure(preview_config)
picam2.start()

# Main loop to show the preview
while True:
    # Capture frame from the camera
    frame = picam2.capture_array()

    # Display the frame in a window
    cv2.imshow("Camera Preview", frame)

    # Exit the loop if the 'q' key is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the camera and close the window
picam2.stop()
cv2.destroyAllWindows()
