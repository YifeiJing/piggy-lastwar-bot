import cv2
import numpy as np
import onnxruntime as ort

class GameObjectDetector:
    def __init__(self, model_path, conf_thres=0.5):
        # 支持 CPUExecutionProvider 或 DmlExecutionProvider (Windows DirectML)
        ort.preload_dlls()
        self.session = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider"])
        self.conf_thres = conf_thres
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape[2:]  # (640, 640)

    def preprocess(self, img_bgr):
        h, w = img_bgr.shape[:2]
        # 等比缩放并 Padding (Letterbox)
        scale = min(self.input_shape[0] / h, self.input_shape[1] / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        
        canvas = np.full((self.input_shape[0], self.input_shape[1], 3), 114, dtype=np.uint8)
        canvas[(self.input_shape[0] - nh) // 2 : (self.input_shape[0] - nh) // 2 + nh,
               (self.input_shape[1] - nw) // 2 : (self.input_shape[1] - nw) // 2 + nw] = resized
        
        # 归一化并转置为 NCHW
        blob = canvas[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.expand_dims(blob, axis=0), scale, (self.input_shape[1] - nw) // 2, (self.input_shape[0] - nh) // 2

    def detect(self, screenshot_bgr):
        blob, scale, pad_x, pad_y = self.preprocess(screenshot_bgr)
        outputs = self.session.run(None, {self.input_name: blob})[0]
        
        # 解析输出并转换回原始图像坐标系
        # outputs shape: [1, num_classes + 4, num_anchors]
        predictions = np.squeeze(outputs).T
        boxes = predictions[:, :4]
        scores = predictions[:, 4:]
        
        class_ids = np.argmax(scores, axis=1)
        confidences = np.max(scores, axis=1)
        
        mask = confidences >= self.conf_thres
        boxes, confidences, class_ids = boxes[mask], confidences[mask], class_ids[mask]
        
        results = []
        for box, conf, cls_id in zip(boxes, confidences, class_ids):
            # 将 (cx, cy, w, h) 转为原始图像坐标
            cx, cy, w, h = box
            x1 = int((cx - w / 2 - pad_x) / scale)
            y1 = int((cy - h / 2 - pad_y) / scale)
            x2 = int((cx + w / 2 - pad_x) / scale)
            y2 = int((cy + h / 2 - pad_y) / scale)
            results.append({"class_id": int(cls_id), "confidence": float(conf), "box": [x1, y1, x2, y2]})
            
        return results