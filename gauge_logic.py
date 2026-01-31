import cv2
import numpy as np
import easyocr

class GaugeReader:
    def __init__(self):
        # Initialize OCR (runs on Pi CPU)
        self.reader = easyocr.Reader(['en'], gpu=False)
        # Constants for your specific gauge (Adjust these!)
        self.TARGET_W = 150
        self.TARGET_H = 600

    def get_warped_gauge(self, frame, x, y, w, h):
        """Straightens the gauge into a vertical strip."""
        source_pts = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
        dest_pts = np.float32([[0, 0], [self.TARGET_W, 0], [self.TARGET_W, self.TARGET_H], [0, self.TARGET_H]])
        
        matrix = cv2.getPerspectiveTransform(source_pts, dest_pts)
        return cv2.warpPerspective(frame, matrix, (self.TARGET_W, self.TARGET_H))

    def find_water_line(self, warped_img):
        """Detects the horizontal transition where water meets air."""
        gray = cv2.cvtColor(warped_img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        
        # Sobel Y finds horizontal edges
        sobel_y = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=3)
        sobel_y = np.absolute(sobel_y)
        
        # Sum intensity across rows
        row_sums = np.sum(sobel_y, axis=1)
        
        # Find the peak (the line)
        line_y = np.argmax(row_sums)
        return line_y

    def read_level(self, warped_img, water_y):
        """Reads numbers and calculates height based on water line."""
        results = self.reader.readtext(warped_img)
        
        for (bbox, text, prob) in results:
            if text.isdigit() and prob > 0.5:
                # Calculate center of the number
                digit_y = (bbox[0][1] + bbox[2][1]) / 2
                
                # Math: If text is '50' (cm) and water is 20px below it
                # You'll need to calibrate 'pixels_per_cm' based on your gauge
                pixels_per_cm = 5.0 
                diff_cm = (water_y - digit_y) / pixels_per_cm
                final_level = int(text) - diff_cm
                
                return round(final_level, 2), text
        return None, None