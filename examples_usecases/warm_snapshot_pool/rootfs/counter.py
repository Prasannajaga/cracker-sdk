import itertools
import sys
import time

print("counter process started", flush=True)

for counter in itertools.count():
    print(f"counter={counter}", flush=True)
    time.sleep(1)