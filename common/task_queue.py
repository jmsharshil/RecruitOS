# common/task_queue.py
import threading
import queue
import time
import logging

logger = logging.getLogger(__name__)

class BackgroundTaskQueue:
    def __init__(self, worker_count=2, max_retries=5):
        self.queue = queue.Queue()
        self.max_retries = max_retries

        for i in range(worker_count):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            logger.info(f"[TASK] Worker-{i+1} started")

    def enqueue(self, fn, *args, **kwargs):
        self.queue.put({"fn": fn, "args": args, "kwargs": kwargs, "attempt": 1})

    def schedule_periodic(self, fn, interval_seconds: int, *args, **kwargs):
        """
        Schedule a function to run periodically via the task queue.
        First execution is immediate; subsequent runs every `interval_seconds`.
        Uses internal daemon Timer (no direct threading usage in calling code).
        """
        def _reschedule():
            self.enqueue(fn, *args, **kwargs)
            timer = threading.Timer(interval_seconds, _reschedule)
            timer.daemon = True
            timer.start()

        # Immediate first run via queue
        self.enqueue(fn, *args, **kwargs)
        # Schedule the periodic reschedules
        timer = threading.Timer(interval_seconds, _reschedule)
        timer.daemon = True
        timer.start()
        logger.info(
            "[TASK] Periodic scheduler started for %s every %ds",
            fn.__name__, interval_seconds
        )

    def _worker(self):
        while True:
            task = self.queue.get()

            fn = task["fn"]
            args = task["args"]
            kwargs = task["kwargs"]
            attempt = task["attempt"]

            try:
                fn(*args, **kwargs)
                logger.info(f"[TASK] Completed {fn.__name__}")
            except Exception as e:
                logger.error(f"[TASK] Failed {fn.__name__}: {e}")

                if attempt < self.max_retries:
                    task["attempt"] += 1
                    logger.info(f"[TASK] Retrying ({attempt}/{self.max_retries})...")
                    time.sleep(2 ** attempt)
                    self.queue.put(task)
                else:
                    logger.error(f"[TASK] Max retries reached for {fn.__name__}")

            self.queue.task_done()


# global background queue
TASK_QUEUE = BackgroundTaskQueue(worker_count=3, max_retries=5)
