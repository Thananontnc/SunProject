"""Train a YOLO fire detector on your own PC (e.g. NVIDIA RTX 4060) and export it for Raspberry Pi 5.

Usage (Windows / Linux, inside the venv - see training/README.md):
    python train_fire.py                         # download D-Fire, train 50 epochs, export
    python train_fire.py --epochs 100
    python train_fire.py --resume                # continue after a crash / shutdown
    python train_fire.py --data-root D:\\dfire     # use a dataset you downloaded yourself
    python train_fire.py --extra D:\\my_roboflow   # add your own photos (Roboflow YOLO export)
    python train_fire.py --export-only           # just export the last best.pt again

Result: runs/fire/weights/best.pt and fire_ncnn_model.zip  -> unzip into server/models/ on the Pi.
"""
import argparse
import glob
import os
import shutil
import sys
from collections import Counter

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
BEST = os.path.join(RUNS, "fire", "weights", "best.pt")
LAST = os.path.join(RUNS, "fire", "weights", "last.pt")
DATA_YAML = os.path.join(HERE, "fire.yaml")
DEFAULT_NAMES = ["smoke", "fire"]  # D-Fire class ids: 0 = smoke, 1 = fire


def find_split(root, names):
    root = root.rstrip("/\\")
    for n in names:
        hits = glob.glob(os.path.join(root, "**", n, "images"), recursive=True) + glob.glob(
            os.path.join(root, "**", "images", n), recursive=True
        )
        if hits:
            return os.path.abspath(sorted(hits, key=len)[0])
    return None


def class_names(root):
    for y in glob.glob(os.path.join(root, "**", "*.yaml"), recursive=True):
        try:
            d = yaml.safe_load(open(y, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and "names" in d:
            n = d["names"]
            return [n[k] for k in sorted(n)] if isinstance(n, dict) else list(n)
    return None


def labels_dir(img_dir):
    p = img_dir.replace(os.sep + "images", os.sep + "labels")
    return p


def count(img_dir, names):
    imgs = [f for f in os.listdir(img_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    c = Counter()
    for f in glob.glob(os.path.join(labels_dir(img_dir), "*.txt")):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                i = int(line.split()[0])
                c[names[i] if i < len(names) else f"id{i}"] += 1
    return len(imgs), dict(c)


def remap_extra(extra_root, names):
    """Make your own dataset's class ids match D-Fire's (by class name)."""
    own = class_names(extra_root)
    if not own:
        sys.exit(f"No data.yaml with class names in {extra_root}")
    remap = {i: names.index(n.lower()) for i, n in enumerate(own) if n.lower() in names}
    print(f"[extra] your classes {own} -> remap {remap}")
    marker = os.path.join(extra_root, ".remapped")
    if os.path.exists(marker):
        print("[extra] already remapped")
        return
    for f in glob.glob(os.path.join(extra_root, "**", "labels", "*.txt"), recursive=True):
        out = []
        for line in open(f, encoding="utf-8"):
            p = line.split()
            if p and int(p[0]) in remap:
                out.append(" ".join([str(remap[int(p[0])])] + p[1:]))
        open(f, "w", encoding="utf-8").write("\n".join(out) + ("\n" if out else ""))
    open(marker, "w").write("done")


def build_yaml(data_root, extra):
    train = find_split(data_root, ["train"])
    val = find_split(data_root, ["val", "valid", "validation"])
    test = find_split(data_root, ["test"])
    if not train:
        sys.exit(f"Could not find train/images under {data_root}. Check the folder layout.")
    val = val or test
    names = class_names(data_root) or DEFAULT_NAMES
    names = [str(n).lower() for n in names]
    print(f"train: {train}\nval:   {val}\ntest:  {test}\nclasses: {dict(enumerate(names))}")
    if "fire" not in names:
        sys.exit("No class called 'fire' in this dataset.")

    data = {"train": train, "val": val, "names": dict(enumerate(names))}
    if test and test != val:
        data["test"] = test
    if extra:
        remap_extra(extra, names)
        et, ev = find_split(extra, ["train"]), find_split(extra, ["valid", "val"])
        if et:
            data["train"] = [train, et]
        if ev:
            data["val"] = [val, ev]
    yaml.safe_dump(data, open(DATA_YAML, "w", encoding="utf-8"))
    for k in ("train", "val", "test"):
        for d in ([data[k]] if isinstance(data.get(k), str) else data.get(k) or []):
            print(f"  {k}: {count(d, names)}  ({d})")
    return data


def export(imgsz, out_dir):
    from ultralytics import YOLO

    if not os.path.exists(BEST):
        sys.exit(f"No trained model at {BEST}")
    best = YOLO(BEST)
    path = best.export(format="ncnn", imgsz=imgsz)
    target = os.path.join(out_dir, "fire_ncnn_model")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(path, target)
    zip_path = shutil.make_archive(os.path.join(out_dir, "fire_ncnn_model"), "zip", out_dir, "fire_ncnn_model")
    print(f"\nDONE  ->  {zip_path}\nCopy it to the Pi and unzip into server/models/  (YOLO_IMGSZ={imgsz})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", help="dataset folder (default: download D-Fire from Kaggle)")
    ap.add_argument("--extra", help="your own Roboflow YOLO export folder to add")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640, help="training image size")
    ap.add_argument("--export-size", type=int, default=320, help="size for the Pi (match YOLO_IMGSZ)")
    ap.add_argument("--batch", type=float, default=0.7, help="-1/0.x = auto by GPU memory fraction, or a number like 32")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", default="yolo26n.pt")
    ap.add_argument("--device", default=None, help="0 = first GPU, cpu, mps")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--export-only", action="store_true")
    a = ap.parse_args()

    import torch
    from ultralytics import YOLO

    print(f"torch {torch.__version__}  CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
    elif a.device is None:
        print("WARNING: no CUDA GPU found -> training on CPU will be VERY slow. See training/README.md step 2.")

    if a.export_only:
        export(a.export_size, HERE)
        return

    if a.resume:
        if not os.path.exists(LAST):
            sys.exit(f"Nothing to resume: {LAST} not found")
        YOLO(LAST).train(resume=True)
    else:
        root = a.data_root
        if not root:
            import kagglehub

            print("Downloading D-Fire (a few GB, first time only)...")
            root = kagglehub.dataset_download("sayedgamal99/smoke-fire-detection-yolo")
        data = build_yaml(root, a.extra)
        batch = int(a.batch) if a.batch >= 1 or a.batch == -1 else a.batch
        YOLO(a.model).train(
            data=DATA_YAML,
            epochs=a.epochs,
            imgsz=a.imgsz,
            batch=batch,
            workers=a.workers,
            patience=15,
            project=RUNS,
            name="fire",
            exist_ok=True,
            cos_lr=True,
            device=a.device,
        )

    # Evaluate
    best = YOLO(BEST)
    d = yaml.safe_load(open(DATA_YAML, encoding="utf-8"))
    m = best.val(data=DATA_YAML, imgsz=a.imgsz, split="test" if "test" in d else "val", project=RUNS, name="val", exist_ok=True)
    print("\n=== Accuracy ===")
    for j, c in enumerate(m.box.ap_class_index):
        print(f"{best.names[int(c)]:>6}: mAP50 = {m.box.ap50[j]:.3f}   mAP50-95 = {m.box.ap[j]:.3f}")
    print("Fire mAP50 > 0.6 = usable, > 0.75 = good. Charts: runs/fire/results.png")

    export(a.export_size, HERE)


if __name__ == "__main__":  # required on Windows (dataloader workers)
    main()
