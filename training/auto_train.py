"""One command: build a better fire dataset, train, test and export for the Pi.

    python auto_train.py               # everything (about 3-5 hours on an RTX 4060)
    python auto_train.py --resume      # continue after the PC shut down
    python auto_train.py --quick       # 3-epoch smoke test (about 10 minutes) to check it runs

What it adds on top of plain D-Fire (train_fire.py):
  1. Small flames: real flames cut out of D-Fire, shrunk to lighter/candle size and pasted on
     other photos (labelled as fire). Plain D-Fire is mostly big fires, so the lighter was missed.
  2. Fake fire: drawn cartoon/printed flames on cloth (shirts), posters and screens, saved with
     EMPTY labels, so the model learns "printed flame = not fire".
  3. Your own Pi camera photos, if you put them in training/my_photos/ (see README):
       my_photos/not_fire/*.jpg      -> fire shirt etc., no labelling needed
       my_photos/fire/images + labels -> real flames with YOLO boxes (Roboflow export)
  4. Trains longer (100 epochs) and exports at 416 px (better for small flames on the Pi).

Result: fire_ncnn_model.zip. On the Pi, unzip into server/models/ and set YOLO_IMGSZ=416.
"""
import argparse
import glob
import os
import random
import shutil
import sys

import cv2
import numpy as np
import yaml

import train_fire as tf

HERE = tf.HERE
GEN = os.path.join(HERE, "generated")
MY = os.path.join(HERE, "my_photos")
IMG_EXT = (".jpg", ".jpeg", ".png")


def images_in(d):
    return sorted(f for f in glob.glob(os.path.join(d, "*")) if f.lower().endswith(IMG_EXT))


def read_labels(img_path, img_dir):
    lab = os.path.join(tf.labels_dir(img_dir), os.path.splitext(os.path.basename(img_path))[0] + ".txt")
    if not os.path.exists(lab):
        return []
    out = []
    for line in open(lab, encoding="utf-8"):
        p = line.split()
        if len(p) == 5:
            out.append([int(p[0])] + [float(v) for v in p[1:]])
    return out


# ------------------------------------------------------------------ sources
def collect(train_dir, fire_id, max_crops=4000, max_bg=4000, seed=0):
    """Fire crops (for small-flame pasting) and fire-free background photos from D-Fire."""
    rnd = random.Random(seed)
    files = images_in(train_dir)
    rnd.shuffle(files)
    crops, bgs = [], []
    for f in files:
        if len(crops) >= max_crops and len(bgs) >= max_bg:
            break
        labs = read_labels(f, train_dir)
        if not labs:
            if len(bgs) < max_bg:
                bgs.append(f)
            continue
        if len(crops) >= max_crops:
            continue
        img = cv2.imread(f)
        if img is None:
            continue
        h, w = img.shape[:2]
        for c, x, y, bw, bh in labs:
            pw, ph = int(bw * w), int(bh * h)
            if c != fire_id or pw < 20 or ph < 20 or pw * ph > 0.25 * w * h:
                continue
            x0, y0 = int((x - bw / 2) * w), int((y - bh / 2) * h)
            crop = img[max(0, y0):y0 + ph, max(0, x0):x0 + pw]
            if crop.size:
                crops.append(crop.copy())
    print(f"[collect] {len(crops)} fire crops, {len(bgs)} fire-free backgrounds")
    return crops, bgs


def load_bg(path, rnd, size=640):
    img = cv2.imread(path) if path else None
    if img is None:  # plain wall / room-like background
        img = np.full((size, size, 3), [rnd.randint(40, 230)] * 3, np.uint8)
        img = cv2.add(img, np.random.randint(0, 25, img.shape, dtype=np.uint8))
    s = size / max(img.shape[:2])
    return cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)))


# ------------------------------------------------------------------ 1. small real flames (labelled)
def paste_small_flame(bg, crop, rnd):
    h, w = bg.shape[:2]
    target_h = rnd.randint(14, max(16, h // 6))  # lighter / candle size
    s = min(target_h / crop.shape[0], (w // 4) / crop.shape[1])  # wide crops must still fit
    fw, fh = max(6, int(crop.shape[1] * s)), max(8, int(crop.shape[0] * s))
    fl = cv2.resize(crop, (fw, fh), interpolation=cv2.INTER_AREA).astype(np.float32)
    # soft oval mask so the paste has no hard rectangle edge
    mask = np.zeros((fh, fw), np.float32)
    cv2.ellipse(mask, (fw // 2, fh // 2), (max(1, fw // 2 - 1), max(1, fh // 2 - 1)), 0, 0, 360, 1.0, -1)
    k = max(3, (min(fw, fh) // 4) | 1)
    mask = cv2.GaussianBlur(mask, (k, k), 0)[..., None]
    x0, y0 = rnd.randint(0, w - fw), rnd.randint(0, h - fh)
    roi = bg[y0:y0 + fh, x0:x0 + fw].astype(np.float32)
    # flames are light sources: brighten (screen blend) rather than cover
    blend = 255 - (255 - roi) * (255 - fl) / 255
    bg[y0:y0 + fh, x0:x0 + fw] = (roi * (1 - mask) + blend * mask).astype(np.uint8)
    return (x0 + fw / 2) / w, (y0 + fh / 2) / h, fw / w, fh / h


# ------------------------------------------------------------------ 2. printed / cartoon flames (no label)
PALETTES = [
    [(0, 0, 200), (0, 120, 255), (0, 230, 255)],        # red, orange, yellow (BGR)
    [(30, 30, 180), (0, 90, 240), (80, 200, 255)],
    [(0, 0, 255), (0, 165, 255)],
    [(20, 20, 140), (0, 60, 220), (0, 140, 255), (120, 230, 255)],
]


def flame_polygon(cx, base_y, width, height, rnd, tongues):
    """Classic printed 'tribal' flame: a row of pointy tongues on a rounded base."""
    pts = [(cx - width / 2, base_y)]
    for i in range(tongues):
        tx = cx - width / 2 + width * (i + 0.5) / tongues + rnd.uniform(-0.1, 0.1) * width / tongues
        th = height * rnd.uniform(0.45, 1.0)
        lean = rnd.uniform(-0.35, 0.35) * width / tongues
        pts.append((tx - width / tongues * 0.45, base_y - th * 0.35))
        pts.append((tx + lean, base_y - th))
        pts.append((tx + width / tongues * 0.45, base_y - th * 0.35))
    pts.append((cx + width / 2, base_y))
    pts.append((cx, base_y + height * 0.12))
    return np.array(pts, np.int32)


def draw_fake_flames(canvas, rnd):
    h, w = canvas.shape[:2]
    pal = rnd.choice(PALETTES)
    width = rnd.uniform(0.25, 0.8) * w
    height = rnd.uniform(0.3, 0.9) * h
    cx, base = w / 2 + rnd.uniform(-0.1, 0.1) * w, h * rnd.uniform(0.75, 0.98)
    tongues = rnd.randint(3, 8)
    # layers: outer colour, then smaller inner colours (flat print look)
    for i, col in enumerate(pal):
        f = 1 - i * 0.22
        poly = flame_polygon(cx, base, width * f, height * f, rnd, tongues)
        cv2.fillPoly(canvas, [poly], col, cv2.LINE_AA)
        if i == 0 and rnd.random() < 0.5:
            cv2.polylines(canvas, [poly], True, (0, 0, 0), rnd.randint(2, 5), cv2.LINE_AA)
    return canvas


def fake_fire_patch(rnd, ph, pw):
    """A shirt / poster / screen with printed flames on it."""
    kind = rnd.choice(["shirt", "shirt", "poster", "screen"])
    if kind == "shirt":
        base = rnd.choice([(20, 20, 20), (40, 40, 40), (230, 230, 230), (120, 60, 20), (60, 60, 140), (30, 90, 30)])
    elif kind == "poster":
        base = (rnd.randint(150, 255),) * 3
    else:
        base = (10, 10, 10)
    patch = np.full((ph, pw, 3), base, np.uint8)
    # Only drawn flames, never real flame photos: "real-looking flame = no fire" would hurt detection.
    patch = draw_fake_flames(patch, rnd)
    if kind == "shirt":
        # fabric: weave noise + soft folds
        noise = np.random.normal(0, 9, patch.shape).astype(np.float32)
        yy = np.linspace(0, rnd.uniform(4, 12) * np.pi, ph)[:, None]
        xx = np.linspace(0, rnd.uniform(2, 6) * np.pi, pw)[None, :]
        folds = (np.sin(yy + xx * rnd.uniform(-0.5, 0.5)) * rnd.uniform(10, 35))[..., None]
        patch = np.clip(patch.astype(np.float32) + noise + folds, 0, 255).astype(np.uint8)
        # slight bend so the print isn't perfectly flat
        src = np.float32([[0, 0], [pw, 0], [0, ph], [pw, ph]])
        j = 0.08
        dst = np.float32([[rnd.uniform(0, j) * pw, rnd.uniform(0, j) * ph], [pw - rnd.uniform(0, j) * pw, rnd.uniform(0, j) * ph],
                          [rnd.uniform(0, j) * pw, ph - rnd.uniform(0, j) * ph], [pw - rnd.uniform(0, j) * pw, ph - rnd.uniform(0, j) * ph]])
        patch = cv2.warpPerspective(patch, cv2.getPerspectiveTransform(src, dst), (pw, ph), borderMode=cv2.BORDER_REFLECT)
    if kind == "screen":
        patch = cv2.add(patch, np.full_like(patch, 25))  # glow
    return patch


def place_patch(bg, patch, rnd):
    h, w = bg.shape[:2]
    ph, pw = patch.shape[:2]
    x0, y0 = rnd.randint(0, w - pw), rnd.randint(0, h - ph)
    bg[y0:y0 + ph, x0:x0 + pw] = patch
    return bg


def camera_look(img, rnd):
    """Pi camera-ish: blur, exposure, colour cast, noise, JPEG."""
    if rnd.random() < 0.5:
        img = cv2.GaussianBlur(img, (3, 3), 0)
    img = cv2.convertScaleAbs(img, alpha=rnd.uniform(0.7, 1.3), beta=rnd.uniform(-30, 30))
    cast = np.array([rnd.uniform(0.85, 1.15) for _ in range(3)], np.float32)
    img = np.clip(img.astype(np.float32) * cast + np.random.normal(0, rnd.uniform(1, 6), img.shape), 0, 255).astype(np.uint8)
    return img


# ------------------------------------------------------------------ build generated dataset
def build_generated(train_dir, fire_id, n_small, n_fake, seed=0):
    marker = os.path.join(GEN, f".done_{n_small}_{n_fake}")
    if os.path.exists(marker):
        print(f"[generate] already built in {GEN}")
        return
    shutil.rmtree(GEN, ignore_errors=True)
    rnd = random.Random(seed)
    np.random.seed(seed)
    crops, bgs = collect(train_dir, fire_id, seed=seed)
    if not crops:
        sys.exit("No fire boxes found in the dataset - cannot make small-flame images.")
    for split in ("train", "val"):
        os.makedirs(os.path.join(GEN, split, "images"), exist_ok=True)
        os.makedirs(os.path.join(GEN, split, "labels"), exist_ok=True)

    def save(split, name, img, labels):
        cv2.imwrite(os.path.join(GEN, split, "images", name + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, rnd.randint(70, 95)])
        with open(os.path.join(GEN, split, "labels", name + ".txt"), "w") as f:
            f.write("".join(f"{fire_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n" for x, y, w, h in labels))

    for i in range(n_small):
        split = "val" if i % 10 == 0 else "train"
        bg = load_bg(rnd.choice(bgs) if bgs and rnd.random() < 0.8 else None, rnd)
        labels = [paste_small_flame(bg, rnd.choice(crops), rnd) for _ in range(rnd.choice([1, 1, 1, 2, 3]))]
        save(split, f"small_{i:05d}", camera_look(bg, rnd), labels)
        if i % 500 == 0:
            print(f"[generate] small flames {i}/{n_small}")

    for i in range(n_fake):
        split = "val" if i % 10 == 0 else "train"
        bg = load_bg(rnd.choice(bgs) if bgs and rnd.random() < 0.8 else None, rnd)
        h, w = bg.shape[:2]
        for _ in range(rnd.choice([1, 1, 2])):
            ph, pw = int(h * rnd.uniform(0.25, 0.8)), int(w * rnd.uniform(0.2, 0.7))
            bg = place_patch(bg, fake_fire_patch(rnd, ph, pw), rnd)
        # some images also contain a REAL small flame (labelled), so the model learns the difference
        labels = [paste_small_flame(bg, rnd.choice(crops), rnd)] if rnd.random() < 0.15 else []
        save(split, f"fake_{i:05d}", camera_look(bg, rnd), labels)
        if i % 500 == 0:
            print(f"[generate] fake fire {i}/{n_fake}")
    open(marker, "w").write("ok")
    print(f"[generate] done -> {GEN}")


def add_my_photos(fire_id):
    """my_photos/not_fire/*.jpg -> empty labels. my_photos/fire -> Roboflow export (used as-is)."""
    dirs = {"train": [], "val": []}
    nf = os.path.join(MY, "not_fire")
    if os.path.isdir(nf) and images_in(nf):
        out = os.path.join(GEN, "my_not_fire")
        for split in ("train", "val"):
            os.makedirs(os.path.join(out, split, "images"), exist_ok=True)
            os.makedirs(os.path.join(out, split, "labels"), exist_ok=True)
        files = images_in(nf)
        for i, f in enumerate(files):
            split = "val" if i % 5 == 0 else "train"
            name = f"my_{i:05d}" + os.path.splitext(f)[1].lower()
            shutil.copy(f, os.path.join(out, split, "images", name))
            open(os.path.join(out, split, "labels", os.path.splitext(name)[0] + ".txt"), "w").close()
        print(f"[my_photos] {len(files)} not-fire photos added")
        for split in ("train", "val"):
            dirs[split].append(os.path.join(out, split, "images"))
    fire = os.path.join(MY, "fire")
    if os.path.isdir(fire):
        names = tf.class_names(fire)
        if names:
            tf.remap_extra(fire, ["smoke", "fire"] if fire_id == 1 else ["fire"])
        for split, keys in (("train", ["train"]), ("val", ["valid", "val"])):
            d = tf.find_split(fire, keys)
            if d:
                dirs[split].append(d)
                print(f"[my_photos] fire {split}: {d}")
    return dirs


# ------------------------------------------------------------------ false-alarm test
def false_alarm_report(model, imgsz, conf):
    val = os.path.join(GEN, "val", "images")
    fakes = [f for f in images_in(val) if os.path.basename(f).startswith("fake_") and os.path.getsize(tf.labels_dir(val) + "/" + os.path.basename(f)[:-4] + ".txt") == 0]
    smalls = [f for f in images_in(val) if os.path.basename(f).startswith("small_")]
    my_nf = images_in(os.path.join(GEN, "my_not_fire", "val", "images"))

    def hit_rate(files):
        if not files:
            return None
        hits = 0
        for i in range(0, len(files), 32):
            for r in model.predict(files[i:i + 32], imgsz=imgsz, conf=conf, verbose=False):
                hits += any(model.names[int(c)] == "fire" for c in r.boxes.cls)
        return hits / len(files)

    print(f"\n=== Real-life check (conf {conf}, size {imgsz}) ===")
    fa = hit_rate(fakes)
    print(f"Printed/cartoon fire wrongly called fire: {fa:.1%}  (lower is better, aim < 5%)")
    sm = hit_rate(smalls)
    print(f"Small real flames found:                  {sm:.1%}  (higher is better, aim > 70%)")
    my = hit_rate(my_nf)
    if my is not None:
        print(f"Your own not-fire photos called fire:     {my:.1%}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--small", type=int, default=3000, help="small-flame images to generate")
    ap.add_argument("--fake", type=int, default=2500, help="printed/cartoon fire images to generate")
    ap.add_argument("--export-size", type=int, default=416, help="size for the Pi (set YOLO_IMGSZ to the same)")
    ap.add_argument("--batch", type=float, default=0.7)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", default="yolo26n.pt")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--quick", action="store_true", help="tiny run to check everything works")
    a = ap.parse_args()
    if a.quick:
        a.epochs, a.small, a.fake = 3, 200, 200

    import torch
    from ultralytics import YOLO

    print(f"torch {torch.__version__}  CUDA: {torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        print("WARNING: no CUDA GPU - this will be very slow. See training/README.md step 2.")

    if a.resume:
        if not os.path.exists(tf.LAST):
            sys.exit(f"Nothing to resume: {tf.LAST} not found")
        YOLO(tf.LAST).train(resume=True)
    else:
        import kagglehub

        print("Getting D-Fire (downloads the first time only)...")
        root = kagglehub.dataset_download("sayedgamal99/smoke-fire-detection-yolo")
        data = tf.build_yaml(root, None)
        names = [data["names"][k] for k in sorted(data["names"])]
        fire_id = names.index("fire")

        build_generated(data["train"], fire_id, a.small, a.fake)
        mine = add_my_photos(fire_id)
        data["train"] = [data["train"], os.path.join(GEN, "train", "images")] + mine["train"]
        data["val"] = [data["val"], os.path.join(GEN, "val", "images")] + mine["val"]
        yaml.safe_dump(data, open(tf.DATA_YAML, "w", encoding="utf-8"))
        print("[data] train sets:", *data["train"], sep="\n   ")

        batch = int(a.batch) if a.batch >= 1 or a.batch == -1 else a.batch
        YOLO(a.model).train(
            data=tf.DATA_YAML, epochs=a.epochs, imgsz=640, batch=batch, workers=a.workers,
            patience=25, project=tf.RUNS, name="fire", exist_ok=True, cos_lr=True,
            hsv_h=0.01,          # keep flame colours close to real (default 0.015)
            scale=0.7,           # more zoom in/out -> more small flames
            mosaic=1.0, close_mosaic=15, mixup=0.05,
        )

    best = YOLO(tf.BEST)
    d = yaml.safe_load(open(tf.DATA_YAML, encoding="utf-8"))
    m = best.val(data=tf.DATA_YAML, imgsz=640, split="test" if "test" in d else "val", project=tf.RUNS, name="val", exist_ok=True)
    print("\n=== Accuracy (D-Fire test) ===")
    for j, c in enumerate(m.box.ap_class_index):
        print(f"{best.names[int(c)]:>6}: mAP50 = {m.box.ap50[j]:.3f}")
    false_alarm_report(best, a.export_size, 0.5)

    tf.export(a.export_size, HERE)
    print(f"\nOn the Pi: unzip into ~/SunProject/server/models/, add YOLO_IMGSZ={a.export_size} to "
          "server/fire-monitor.env, then: sudo systemctl restart fire-monitor")


if __name__ == "__main__":
    main()
