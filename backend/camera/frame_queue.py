from collections import deque


def create_frame_queues():
    """Create the shared frame queues used between threads.

    Returns:
        tuple: (frame_q, cropped_raw_frame_q, debug_frame_q)
    """
    frame_q = deque(maxlen=20)
    cropped_raw_frame_q = deque(maxlen=3)
    debug_frame_q = deque(maxlen=3)
    return frame_q, cropped_raw_frame_q, debug_frame_q
