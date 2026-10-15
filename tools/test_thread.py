import threading
import time

def thread_worker():
    time.sleep(0.5)
    raise ValueError("Something went wrong in the worker thread!")

t = threading.Thread(target=thread_worker)
t.start()

# t.join()
print("Main thread finished successfully!")
while(t.is_alive()):
    print('Still alive')
    time.sleep(0.5)
print(f"Worker thread is {'Alive' if t.is_alive() else 'dead'}")