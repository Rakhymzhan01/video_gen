"""
Video Worker - Placeholder until full implementation
"""
import time
import signal
import sys

class VideoWorker:
    def __init__(self):
        self.running = True
        
    def stop(self, signum, frame):
        print("Stopping video worker...")
        self.running = False
        
    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        
        print("Video worker started")
        while self.running:
            time.sleep(5)
            print("Video worker is running...")
        
        print("Video worker stopped")

if __name__ == "__main__":
    worker = VideoWorker()
    worker.run()