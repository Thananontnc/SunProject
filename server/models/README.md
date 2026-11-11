# Models

`fire_ncnn_model/` is the trained fire detector, and the server loads it automatically.

- Model: YOLO26n, trained on the D-Fire dataset (smoke and fire) for 50 epochs on an RTX 4060.
- Test accuracy: fire mAP50 0.72 (precision 0.73, recall 0.64), all classes mAP50 0.78.
- Export: NCNN at image size 320 (`YOLO_IMGSZ=320`). Class ids are `0=smoke` and `1=fire`.
- Runtime: on the Pi it needs only `pip install ncnn` (no PyTorch). It takes about 14 ms per frame on a Pi 5.

To replace it, unzip a new `fire_ncnn_model.zip` from `training/train_fire.py` here.
If this folder is missing, the server falls back to the colour detector.
