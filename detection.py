import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
import time
from datetime import datetime
import serial
import serial.tools.list_ports

class FlashlightDetector:
    def __init__(self):
        self.detection_params = {
            'brightness_threshold': 230,
            'flash_threshold': 500,  # milliseconds
            'min_area': 500
        }
        self.flash_count = 0
        self.torch_on = False
        self.last_torch_time = 0
        self.flash_times = []
        self.is_processing = True
        self.debug_mode = False  # Add debug mode flag

        # Initialize camera
        self.setup_camera()
        
        # Initialize Arduino
        self.arduino = None
        self.setup_arduino()
        
        self.setup_gui()
        self.process_frames()

    def setup_camera(self):
        """Initialize and configure the camera with error handling."""
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                raise Exception("Could not access camera")
            
            # Set camera properties for better performance
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
        except Exception as e:
            raise Exception(f"Camera initialization error: {str(e)}")

    def setup_arduino(self):
        """Initialize Arduino connection with port detection."""
        try:
            # Automatically find Arduino port
            arduino_ports = [
                p.device
                for p in serial.tools.list_ports.comports()
                if 'Arduino' in p.description or 'CH340' in p.description  # Common Arduino identifiers
            ]
            
            if not arduino_ports:
                raise Exception("No Arduino found. Please check connection.")
                
            self.arduino = serial.Serial(port=arduino_ports[0], baudrate=9600, timeout=1)
            time.sleep(2)  # Wait for connection to stabilize
            
            # Test connection
            self.arduino.write(b'TEST\n')
            response = self.arduino.readline().decode().strip()
            if response != "OK":
                raise Exception("Arduino communication test failed")
                
        except Exception as e:
            messagebox.showerror("Arduino Error", f"Error connecting to Arduino: {str(e)}")
            self.arduino = None

    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Flashlight Detection System")
        self.root.configure(bg='#121212')

        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Status displays
        self.flash_count_var = tk.StringVar(value="Flash Count: 0")
        ttk.Label(main_frame, textvariable=self.flash_count_var).grid(row=0, column=0, padx=5, pady=5)

        self.status_var = tk.StringVar(value="Status: Initializing...")
        ttk.Label(main_frame, textvariable=self.status_var).grid(row=1, column=0, padx=5, pady=5)

        # Control buttons
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, pady=10)

        ttk.Button(control_frame, text="Reset Count", command=self.reset_count).grid(row=0, column=0, padx=5)
        ttk.Button(control_frame, text="Toggle Debug", command=self.toggle_debug).grid(row=0, column=1, padx=5)
        
        # Debug info
        self.debug_var = tk.StringVar(value="Debug Info: Disabled")
        self.debug_label = ttk.Label(main_frame, textvariable=self.debug_var)
        self.debug_label.grid(row=3, column=0, pady=5)

    def reset_count(self):
        """Reset the flash count and update the display."""
        self.flash_count = 0
        self.flash_times = []
        self.flash_count_var.set("Flash Count: 0")
        self.status_var.set("Status: Count reset")

    def toggle_debug(self):
        """Toggle debug mode on/off."""
        self.debug_mode = not self.debug_mode
        self.debug_var.set(f"Debug Info: {'Enabled' if self.debug_mode else 'Disabled'}")

    def process_frames(self):
        if not self.is_processing:
            return

        try:
            ret, frame = self.cap.read()
            if not ret:
                raise Exception("Failed to read camera frame")

            # Process frame
            processed_frame = self.detect_flashlight(frame)
            
            # Show debug information
            if self.debug_mode:
                self.show_debug_info(processed_frame)
            
            cv2.imshow("Flashlight Detection", processed_frame)
            cv2.waitKey(1)

        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")

        self.root.after(10, self.process_frames)

    def detect_flashlight(self, frame):
        """Process frame to detect flashlight."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_bound = np.array([0, 0, self.detection_params['brightness_threshold']])
        upper_bound = np.array([180, 25, 255])
        mask = cv2.inRange(hsv, lower_bound, upper_bound)
        blurred_mask = cv2.GaussianBlur(mask, (5, 5), 0)

        contours, _ = cv2.findContours(blurred_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        current_time = time.time() * 1000
        torch_detected = self.process_contours(frame, contours, current_time)
        
        if not torch_detected and self.torch_on:
            self.last_torch_time = current_time
            self.torch_on = False
        
        return frame

    def process_contours(self, frame, contours, current_time):
        """Process detected contours and handle flash detection logic."""
        torch_detected = False
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > self.detection_params['min_area']:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                torch_detected = True

        if torch_detected and not self.torch_on:
            if current_time - self.last_torch_time > self.detection_params['flash_threshold']:
                self.handle_flash_detection(current_time)
                
        return torch_detected

    def handle_flash_detection(self, current_time):
        """Handle flash detection and Arduino communication."""
        self.flash_times.append(current_time)
        self.flash_times = [t for t in self.flash_times if current_time - t <= 2000]
        
        self.flash_count = len(self.flash_times)
        self.flash_count_var.set(f"Flash Count: {self.flash_count}")
        self.status_var.set("Status: Flash detected!")
        
        if self.flash_count == 2:
            self.dim_light()
        
        self.torch_on = True

    def dim_light(self):
        """Send command to Arduino to dim the light with error handling."""
        if not self.arduino or not self.arduino.is_open:
            self.status_var.set("Error: Arduino not connected")
            return
            
        try:
            self.arduino.write(b'DIM\n')
            response = self.arduino.readline().decode().strip()
            if response == "OK":
                self.status_var.set("Status: Light dimmed successfully!")
                self.root.after(10000, self.reset_light)
            else:
                self.status_var.set("Error: Failed to dim light")
        except Exception as e:
            self.status_var.set(f"Arduino communication error: {str(e)}")

    def show_debug_info(self, frame):
        """Display debug information on frame."""
        debug_text = [
            f"Flash Count: {self.flash_count}",
            f"Torch On: {self.torch_on}",
            f"Last Flash: {int(time.time() * 1000 - self.last_torch_time)}ms ago"
        ]
        
        y = 30
        for text in debug_text:
            cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (0, 255, 0), 2)
            y += 30

    def reset_light(self):
        """Send command to Arduino to reset the light."""
        if not self.arduino or not self.arduino.is_open:
            self.status_var.set("Error: Arduino not connected")
            return
            
        try:
            self.arduino.write(b'RESET\n')
            response = self.arduino.readline().decode().strip()
            if response == "OK":
                self.status_var.set("Status: Light reset successfully!")
            else:
                self.status_var.set("Error: Failed to reset light")
        except Exception as e:
            self.status_var.set(f"Arduino communication error: {str(e)}")

    def cleanup(self):
        """Clean up resources properly."""
        self.is_processing = False
        if self.cap.isOpened():
            self.cap.release()
        if self.arduino and self.arduino.is_open:
            self.arduino.write(b'RESET\n')  # Reset light before closing
            self.arduino.close()
        cv2.destroyAllWindows()
        self.root.destroy()

if __name__ == "__main__":
    try:
        detector = FlashlightDetector()
        detector.run()
    except Exception as e:
        messagebox.showerror("Error", f"Application error: {str(e)}")
