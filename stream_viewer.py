import cv2
import time

def stream_remote_rtsp(rtsp_url, reconnect_delay=5):
    print(f"Connecting to RTSP stream: {rtsp_url}")
    
    while True:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print(f"Error: Unable to connect. Retrying in {reconnect_delay}s...")
            time.sleep(reconnect_delay)
            continue

        print("Stream connected. Displaying feed (Press 'q' to quit).")

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("Stream interrupted. Reconnecting...")
                    break

                cv2.imshow("Remote IoT RTSP Stream", frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    cap.release()
                    cv2.destroyAllWindows()
                    return

        except Exception as e:
            print(f"An error occurred: {e}")
        
        finally:
            cap.release()
            cv2.destroyAllWindows()

        time.sleep(reconnect_delay)

if __name__ == "__main__":
    REMOTE_CAMERA_URL = "rtsp://admin:password@192.168.1.50:554/h264Preview_01_main"
    stream_remote_rtsp(REMOTE_CAMERA_URL)
