def test_queue_add():
    queue = []
    queue.append("song1.mp3")
    assert len(queue) == 1
    assert queue[0] == "song1.mp3"

def test_queue_empty():
    queue = []
    assert len(queue) == 0