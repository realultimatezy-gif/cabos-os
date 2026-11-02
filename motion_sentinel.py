import cv2
import numpy as np
import os
import requests
from datetime import datetime

# Configuration variables (Replace with your actual keys/URLs if needed)
TELEGRAM_BOT_TOKEN = "123456:ABC-DEF"
TELEGRAM_CHAT_ID = "@your_alert_channel"
DISCORD_WEBHOOK_URL = "" # Optional: Add Discord webhook URL here

def send_telegram_alert(image_path, caption):
    if not TELEGRAM_BOT_TOKEN or "123456" in TELEGRAM_BOT_TOKEN:
        print("[Mock Alert] Telegram notification skipped (Token not configured).")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, 'rb') as photo:
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
            files = {'photo': photo}
            response = requests.post(url, data=payload, files=files, timeout=10)
            if response.status_code == 200:
                print("[Alert Sent] Snapshot successfully sent via Telegram.")
            else:
                print(f"[Alert Failed] Telegram returned status {response.status_code}")
    except Exception as e:
        print(f"[Alert Error] Failed to dispatch Telegram alert: {e}")

def optimized_motion_guard_with_alerts(rtsp_url=0, scale_width=500, sensitivity_area=1500, output_dir="motion_snapshots"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print("Error: Could not open video source.")
        return

    fgbg = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=50, detectShadows=True)
    print("Motion Guard with Automated Alerts running. Press 'q' to exit.")

    # Cooldown timer to prevent flooding alerts during continuous motion
    last_alert_time = 0
    cooldown_seconds = 10

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            height, width = frame.shape[:2]
            aspect_ratio = height / width
            new_height = int(scale_width * aspect_ratio)
            small_frame = cv2.resize(frame, (scale_width, new_height))

            fg_mask = fgbg.apply(small_frame)
            _, thresh = cv2.threshold(fg_mask, 250, 255, cv2.THRESH_BINARY)
            
            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

            motion_pixels = cv2.countNonZero(thresh)
            current_time = datetime.now().timestamp()

            if motion_pixels > sensitivity_area and (current_time - last_alert_time) > cooldown_seconds:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = os.path.join(output_dir, f"alert_{timestamp}.jpg")
                cv2.imwrite(filename, frame)
                
                print(f"[ALERT TRIGGERED] Motion score: {motion_pixels}. Saving snapshot...")
                
                # Dispatch notification alert asynchronously/inline
                alert_caption = f"🚨 Sentinel Security Alert!\nMotion detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                send_telegram_alert(filename, alert_caption)
                
                last_alert_time = current_time

            cv2.imshow("Sentinel Alert Guard", small_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    optimized_motion_guard_with_alerts(rtsp_url=0)
