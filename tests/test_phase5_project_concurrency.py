import threading
import time
from concurrent.futures import ThreadPoolExecutor

from pipeline.queue.resources import resource_limits


def test_project_semaphore_allows_three_and_never_four():
    active = 0
    maximum = 0
    lock = threading.Lock()
    barrier = threading.Barrier(3)

    def worker():
        nonlocal active, maximum
        with resource_limits.reserve("project"):
            with lock:
                active += 1
                maximum = max(maximum, active)
            if active <= 3:
                try:
                    barrier.wait(timeout=1)
                except threading.BrokenBarrierError:
                    pass
            time.sleep(0.05)
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _i: worker(), range(4)))
    assert maximum == 3
