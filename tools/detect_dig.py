from vision.detector import GameObjectDetector
import cv2
import os

def detect_dig_existence(img):
    detector = GameObjectDetector(os.path.join('models', 'dig_model.onnx'))
    res = detector.detect(img)
    if len(les) == 0:
        return False
    else:
        return True

def determine_dig_type(img, detector):
    import time
    start = time.perf_counter()
    res = detector.detect(img)
    end = time.perf_counter()
    print(f'Detection cost: {end-start:.6} seconds')
    if len(res) == 0:
        return -1
    if res[0]['class_id'] == 0:
        print(f'Drone found: {res[0]['box']}')
    elif res[0]['class_id'] == 1:
        print(f'Excavator found: {res[0]['box']}')

if __name__ == "__main__":
    import sys
    import time
    detector = GameObjectDetector(os.path.join('models', 'dig_model.onnx'))

    if len(sys.argv) == 2:
        img = cv2.imread(sys.argv[1])
        determine_dig_type(img, detector)
    if len(sys.argv) == 3 and sys.argv[1] == 'list':
        with open(sys.argv[2], 'r') as f:
            for line in f.readlines():
                buf = line.split(',')
                img = cv2.imread(buf[0])
                determine_dig_type(img, detector)
                print(f'file: {buf[0]}, type: {'drone' if int(buf[1]) == 0 else 'excavator'}')