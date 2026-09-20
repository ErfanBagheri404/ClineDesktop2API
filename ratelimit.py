"""Per-IP token-bucket rate limiter."""
import time
import threading

class RateLimiter:
    def __init__(self, interval):
        self.interval = interval
        self.buckets = {}
        self.lock = threading.Lock()

    def allow(self, ip):
        now = time.time()
        with self.lock:
            last = self.buckets.get(ip, 0)
            if now - last < self.interval:
                wait = self.interval - (now - last)
                return False, wait
            self.buckets[ip] = now
            return True, 0

    def start_cleanup(self):
        def cleanup():
            while True:
                time.sleep(60)
                now = time.time()
                with self.lock:
                    stale = [k for k, v in self.buckets.items() if now - v > 300]
                    for k in stale:
                        del self.buckets[k]
        t = threading.Thread(target=cleanup, daemon=True)
        t.start()
