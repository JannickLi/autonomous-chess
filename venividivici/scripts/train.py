"""
train.py  —  Step 4

Online training: generates synthetic images on-the-fly every epoch — no
files written to disk.

  python scripts/train.py --boards chessboard_one

After every N epochs a 4×4 grid of colour-coded prediction tiles is saved to
validation/epoch_NNNN.jpg.  Green = correct, blue = wrong class,
red (thick) = false positive, red (thin) = missed GT box.

Results land in runs/detect/<name>/
"""

import argparse
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

ROOT     = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"

LABELS = [
    "white-pawn", "white-rook", "white-knight", "white-bishop",
    "white-queen", "white-king",
    "black-pawn", "black-rook", "black-knight", "black-bishop",
    "black-queen", "black-king",
    "corner-a8", "corner-h8", "corner-h1", "corner-a1",   # IDs 12-15
]
COLOR_LABELS = ["white", "black", "corner"]
TYPE_LABELS  = ["pawn", "rook", "knight", "bishop", "queen", "king", "corner"]
LABEL_MODES  = {"combined": LABELS, "color": COLOR_LABELS, "type": TYPE_LABELS}

# ── Online dataset ─────────────────────────────────────────────────────────────

class SynthDataset:
    """
    PyTorch Dataset that generates synthetic board images on-the-fly.
    Training split  — fresh random sample every call (no seed).
    Validation split — deterministic: seeded per index for stable metrics.
    """

    def __init__(self, empty_images: list, piece_crops: dict,
                 n_per_epoch: int, imgsz: int,
                 n_pieces_range: tuple = (1, 32), val_seed: int | None = None,
                 label_mode: str = "combined"):
        import torch
        from augment import synth_one, translate_labels

        self._synth_one     = synth_one
        self._translate     = translate_labels
        self._torch         = torch
        self.n              = n_per_epoch
        self.imgsz          = imgsz
        self.n_pieces_range = n_pieces_range
        self.val_seed       = val_seed
        self.label_mode     = label_mode
        self.empty_images   = empty_images
        self.piece_crops    = piece_crops

        n_crops = sum(len(v) for v in self.piece_crops.values())
        logging.getLogger(__name__).info(
            f"  SynthDataset: {len(self.empty_images)} empty image(s), "
            f"{n_crops} piece crop(s), {n_per_epoch} samples/epoch"
        )

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, index: int) -> dict:
        torch = self._torch
        rng = (random.Random(self.val_seed + index)
               if self.val_seed is not None else random.Random())

        img_pil, yolo_labels = self._synth_one(
            self.empty_images, self.piece_crops, self.n_pieces_range, rng
        )
        yolo_labels = self._translate(yolo_labels, self.label_mode)

        # Keep RGB order — Ultralytics training expects RGB tensors.
        # Do NOT divide by 255 — preprocess_batch does that; doing it here
        # would double-normalise to [0, 0.004] and collapse training.
        img_np = np.array(img_pil)   # (H, W, 3) uint8, RGB
        img_np = cv2.resize(img_np, (self.imgsz, self.imgsz),
                            interpolation=cv2.INTER_LINEAR)
        img_t  = torch.from_numpy(np.ascontiguousarray(img_np)).permute(2, 0, 1).float()

        cls_list, bbox_list = [], []
        for line in yolo_labels:
            parts = line.split()
            cls_list.append([int(parts[0])])
            bbox_list.append([float(p) for p in parts[1:5]])

        n = len(cls_list)
        return {
            "img":           img_t,
            "cls":           torch.tensor(cls_list,  dtype=torch.float32) if n else torch.zeros((0, 1)),
            "bboxes":        torch.tensor(bbox_list, dtype=torch.float32) if n else torch.zeros((0, 4)),
            "batch_idx":     torch.zeros(n),
            "im_file":       f"synth_{index:05d}",
            "ori_shape":     (self.imgsz, self.imgsz),
            "resized_shape": (self.imgsz, self.imgsz),
            "ratio_pad":     ((1.0, 1.0), (0, 0)),
        }

    @staticmethod
    def collate_fn(batch: list) -> dict:
        import torch
        new_batch: dict = {}
        keys   = batch[0].keys()
        values = list(zip(*[list(b.values()) for b in batch]))

        for i, k in enumerate(keys):
            value = list(values[i])
            if k == "img":
                value = torch.stack(value, 0)
            elif k in {"bboxes", "cls"}:
                value = torch.cat(value, 0)
            new_batch[k] = value

        for i in range(len(new_batch["batch_idx"])):
            new_batch["batch_idx"][i] += i
        new_batch["batch_idx"] = torch.cat(new_batch["batch_idx"], 0)
        return new_batch

# ── Online trainer ─────────────────────────────────────────────────────────────

def make_online_trainer(synth_kwargs: dict):
    import torch
    from ultralytics.models.yolo.detect import DetectionTrainer

    class OnlineDetectionTrainer(DetectionTrainer):

        def build_dataset(self, img_path, mode="train", batch=None):
            kw = dict(synth_kwargs)
            if mode == "val":
                kw["n_per_epoch"] = max(kw["n_per_epoch"] // 5, 1)
                kw["val_seed"]    = 42
            return SynthDataset(**kw)

        def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
            dataset = self.build_dataset(dataset_path, mode=mode)
            return torch.utils.data.DataLoader(
                dataset,
                batch_size=batch_size,
                num_workers=self.args.workers,
                shuffle=(mode == "train"),
                drop_last=(mode == "train"),   # avoid partial batches in training
                collate_fn=SynthDataset.collate_fn,
                pin_memory=torch.cuda.is_available(),
                persistent_workers=(self.args.workers > 0),
            )

        def plot_training_labels(self):
            pass

        def save_metrics(self, metrics):
            pass  # suppress results.csv

        def plot_metrics(self):
            pass  # suppress results.png

        def plot_training_samples(self, *a, **kw):
            pass  # suppress train_batchN.jpg

        def plot_val_samples(self, *a, **kw):
            pass  # suppress val_batchN_labels/pred.jpg

    return OnlineDetectionTrainer

# ── data.yaml ─────────────────────────────────────────────────────────────────

def _write_online_yaml(labels: list = LABELS) -> Path:
    data_yaml = ROOT / "dataset" / "data.yaml"
    (ROOT / "dataset").mkdir(exist_ok=True)
    lines = [
        "train: .",
        "val: .",
        f"nc: {len(labels)}",
        "names:",
    ]
    for i, l in enumerate(labels):
        lines.append(f"  {i}: {l}")
    data_yaml.write_text("\n".join(lines) + "\n")
    return data_yaml

# ── Visual validation callback ─────────────────────────────────────────────────

def _make_val_callback(empty_images, piece_crops, n_images, val_every, output_root, label_mode="combined"):
    from augment import synth_one, translate_labels

    all_empty = empty_images
    all_crops = piece_crops

    active_labels = LABEL_MODES[label_mode]
    IOU_THRESH    = 0.3

    def _iou(a, b):
        ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
        ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            return 0.0
        return inter / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter)

    def callback(trainer):
        from ultralytics import YOLO

        epoch = trainer.epoch + 1
        if epoch % val_every != 0:
            return
        last_wts = Path(trainer.last) if hasattr(trainer, "last") else None
        if last_wts is None or not last_wts.exists():
            return
        imgsz = trainer.args.imgsz
        if isinstance(imgsz, (list, tuple)):
            imgsz = imgsz[0]

        infer      = YOLO(str(last_wts))
        rng        = random.Random(epoch)
        tiles      = []
        n_tiles    = (n_images // 4) * 4   # must be a multiple of 4 for the grid
        if n_tiles == 0:
            return

        for _ in range(n_tiles):
            img_pil, gt_labels = synth_one(all_empty, all_crops, (1, 32), rng)
            gt_labels = translate_labels(gt_labels, label_mode)
            img_bgr   = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            img_bgr   = cv2.resize(img_bgr, (imgsz, imgsz))
            result    = infer.predict(img_bgr, imgsz=imgsz, verbose=False, conf=0.3)[0]
            h, w      = img_bgr.shape[:2]

            gt_boxes = []
            for line in gt_labels:
                p = line.split()
                cx, cy, bw_, bh_ = float(p[1]), float(p[2]), float(p[3]), float(p[4])
                gt_boxes.append((
                    int((cx - bw_ / 2) * w), int((cy - bh_ / 2) * h),
                    int((cx + bw_ / 2) * w), int((cy + bh_ / 2) * h),
                    int(p[0]),
                ))

            pred_boxes = []
            for box in result.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                pred_boxes.append((x1, y1, x2, y2, int(box.cls[0]), float(box.conf[0])))

            annotated  = img_bgr.copy()
            gt_matched = [False] * len(gt_boxes)

            for (px1, py1, px2, py2, pcls, pconf) in pred_boxes:
                best_iou, best_idx = 0.0, -1
                for i, (gx1, gy1, gx2, gy2, _) in enumerate(gt_boxes):
                    iou = _iou((px1, py1, px2, py2), (gx1, gy1, gx2, gy2))
                    if iou > best_iou:
                        best_iou, best_idx = iou, i

                if best_iou < IOU_THRESH:
                    colour = (0, 0, 220)
                elif gt_boxes[best_idx][4] != pcls:
                    colour = (200, 80, 0)
                    gt_matched[best_idx] = True
                else:
                    colour = (0, 200, 0)
                    gt_matched[best_idx] = True

                cv2.rectangle(annotated, (px1, py1), (px2, py2), colour, 2)
                cv2.putText(annotated, f"{active_labels[pcls]} {pconf:.2f}",
                            (px1 + 2, py1 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1)

            for (gx1, gy1, gx2, gy2, _), matched in zip(gt_boxes, gt_matched):
                if not matched:
                    cv2.rectangle(annotated, (gx1, gy1), (gx2, gy2), (0, 0, 220), 1)

            tiles.append(annotated)

        cols = 4
        rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
        grid = np.vstack(rows)
        output_root.mkdir(parents=True, exist_ok=True)
        out  = output_root / f"epoch_{epoch:04d}.jpg"
        cv2.imwrite(str(out), grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
        logging.getLogger(__name__).info(f"  [val] epoch {epoch}: {n_images} tiles -> {out}")

    return callback

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8 on chess pieces (online mode).")

    parser.add_argument("--model",       default="yolov8s",
                        help="yolov8n / yolov8s / yolov8m / yolov8l / yolov8x")
    parser.add_argument("--epochs",      type=int, default=1000000)
    parser.add_argument("--imgsz",       type=int, default=1280)
    parser.add_argument("--batch",       type=int, default=16,
                        help="Batch size (-1 for auto).  8 is safe for 1280 on 12 GB VRAM.")
    parser.add_argument("--workers",     type=int, default=0,
                        help="DataLoader worker threads (0 = main process, safest on Windows)")
    parser.add_argument("--device",      default=None,
                        help="Device: 0 | 0,1 | cpu  (auto-detected if omitted)")
    parser.add_argument("--patience",    type=int, default=1000,
                        help="Early-stopping patience in epochs")
    parser.add_argument("--name",        default="chess",
                        help="Run name inside runs/detect/")
    parser.add_argument("--resume",      action="store_true",
                        help="Resume interrupted training from last.pt")
    parser.add_argument("--resume-best", action="store_true",
                        help="Fine-tune from best.pt of the current --name run")
    parser.add_argument("--boards",      nargs="+", default=["chessboard_one"],
                        help="Board names in representation_data/")
    parser.add_argument("--n-per-epoch", type=int, default=128,
                        help="Synthetic images generated per training epoch")
    parser.add_argument("--val-images",  type=int, default=4,
                        help="Images in the per-epoch validation grid (must be a multiple of 4)")
    parser.add_argument("--val-every",   type=int, default=5,
                        help="Save validation grid every N epochs")
    parser.add_argument("--label-mode",  default="combined",
                        choices=["combined", "color", "type"],
                        help="Class space: combined (13 classes), color (3), type (7)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    import torch as _torch
    if args.device is not None:
        device = args.device
    elif _torch.cuda.is_available():
        device = 0
    else:
        logger.warning("No CUDA GPU found — training on CPU (will be slow).")
        device = "cpu"

    try:
        from ultralytics import YOLO
        import ultralytics.utils as _uu
        if hasattr(_uu, "LOGGER"):
            _uu.LOGGER.setLevel(logging.WARNING)
        if hasattr(_uu, "VERBOSE"):
            _uu.VERBOSE = False
    except ImportError:
        raise ImportError("ultralytics not installed.  Run: pip install ultralytics")

    if args.resume_best:
        model_id = str(RUNS_DIR / "detect" / args.name / "weights" / "best.pt")
        if not Path(model_id).exists():
            raise FileNotFoundError(
                f"--resume-best: no best.pt at {model_id}\n"
                f"Run a full training first, or pass --model <path> manually."
            )
        logger.info(f"Fine-tuning from: {model_id}")
    else:
        model_id = args.model if args.model.endswith(".pt") else f"{args.model}.pt"

    from augment import load_board_data

    # Load board data ONCE — reused by train dataset, val dataset, and val callback.
    all_empty = []
    all_crops = {l: [] for l in LABELS}
    for board in args.boards:
        empty_imgs, crops = load_board_data(board)
        all_empty.extend(empty_imgs)
        for label, c in crops.items():
            all_crops[label].extend(c)

    active_labels = LABEL_MODES[args.label_mode]
    data_yaml     = _write_online_yaml(labels=active_labels)

    run_start = datetime.now()
    ts        = run_start.strftime("%Y%m%d_%H%M%S")
    run_name  = args.name if args.resume else f"{args.name}_{ts}"
    val_dir   = ROOT / "validation" / run_name

    logger.info(f"Started : {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Run     : {run_name}")
    logger.info(f"Model   : {model_id}")
    logger.info(f"Boards  : {args.boards}")
    logger.info(f"Labels  : {args.label_mode}  ({len(active_labels)} classes)")
    logger.info(f"Compute : {'CPU' if device == 'cpu' else 'GPU'}")
    logger.info(f"Epochs  : {args.epochs} (early-stop patience={args.patience})  |  imgsz: {args.imgsz}  |  batch: {args.batch}")
    logger.info(f"Samples : {args.n_per_epoch} train + {max(args.n_per_epoch // 5, 1)} val per epoch")
    logger.info(f"Val grid: every {args.val_every} epoch(s), {args.val_images} tiles -> {val_dir}")
    logger.info("")
    logger.info("Losses (lower is better):")
    logger.info("  box_loss  CIoU regression  — 0=perfect, early ~1.5, converged ~0.3-0.6")
    logger.info("  cls_loss  BCE classification — 0=perfect, early ~3-5,  converged ~0.5-1.5")
    logger.info("  dfl_loss  box-edge sharpness — 0=perfect, early ~1.3, converged ~0.9-1.1")
    logger.info("")

    synth_kwargs = dict(
        empty_images  = all_empty,
        piece_crops   = all_crops,
        n_per_epoch   = args.n_per_epoch,
        imgsz         = args.imgsz,
        n_pieces_range= (1, 32),
        label_mode    = args.label_mode,
    )

    val_cb       = _make_val_callback(
        empty_images = all_empty,
        piece_crops  = all_crops,
        n_images     = args.val_images,
        val_every    = args.val_every,
        output_root  = val_dir,
        label_mode   = args.label_mode,
    )

    _log = logging.getLogger(__name__)
    _epoch_t = [None]   # set on first callback so startup time isn't included

    def loss_cb(trainer):
        tloss = getattr(trainer, "tloss", None)
        if tloss is None:
            return
        names = getattr(trainer, "loss_names", ("box_loss", "cls_loss", "dfl_loss"))
        try:
            vals = tloss.tolist() if hasattr(tloss, "tolist") else list(tloss)
        except Exception:
            return
        now = time.monotonic()
        elapsed_str = f"+{now - _epoch_t[0]:.0f}s" if _epoch_t[0] is not None else "---"
        _epoch_t[0] = now
        parts = "  ".join(f"{n}={v:.4f}" for n, v in zip(names, vals))
        _log.info(f"  {datetime.now().strftime('%H:%M:%S')}  epoch {trainer.epoch + 1:>4}  {parts}  ({elapsed_str})")

    model = YOLO(model_id)
    model.add_callback("on_train_epoch_end", loss_cb)
    model.add_callback("on_fit_epoch_end",   val_cb)

    results = model.train(
        data       = str(data_yaml),
        epochs     = args.epochs,
        imgsz      = args.imgsz,
        batch      = args.batch,
        workers    = args.workers,
        patience   = args.patience,
        project    = str(RUNS_DIR / "detect"),
        name       = run_name,
        resume     = args.resume,
        exist_ok   = True,
        save_period= 10,
        plots      = False,
        # With epochs=1e6 the built-in cosine schedule barely moves (LR drops
        # ~0.00001 % after 1000 epochs).  lrf=1.0 makes the flat-LR intent
        # explicit: warmup ramps to lr0, then LR stays constant until early
        # stopping fires.  Proper annealing requires a fixed epoch budget.
        lrf        = 1.0,
        trainer    = make_online_trainer(synth_kwargs),
        verbose    = False,
        device     = device,
    )

    run_end  = datetime.now()
    duration = run_end - run_start
    h, rem   = divmod(int(duration.total_seconds()), 3600)
    m, s     = divmod(rem, 60)
    print(f"\nTraining complete.")
    print(f"Started : {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Finished: {run_end.strftime('%Y-%m-%d %H:%M:%S')}  (duration {h:02d}:{m:02d}:{s:02d})")
    print(f"Best weights: {Path(results.save_dir) / 'weights' / 'best.pt'}")


if __name__ == "__main__":
    main()
