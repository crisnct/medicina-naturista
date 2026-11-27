"""PaddleOCR worker process for extract_pdf_markdown.py; run it with the `.venv-ocr` interpreter.

PaddleOCR needs numpy<2.4 while the project needs numpy>=2.4, so it lives in its own virtual
environment (requirements-ocr.txt) and serves one extraction run as a child process
(pdf_paddle.PaddleSession). Each request is a JSON line, {"op": "read" | "recognize", "width": w,
"height": h, "size": n}, followed by the n = w * h * 3 bytes of an RGB image; each answer is one
ASCII JSON line on stdout. The first answer is {"ready": true} or {"error": ...}.

The models are loaded only from model_cache/paddleocr; the worker never downloads anything, except
when started by hand to fetch them once:

    .venv-ocr/Scripts/python.exe src/scripts/pdf_paddle_worker.py --download
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "model_cache" / "paddleocr"
MODELS = {
    "orientation": "PP-LCNet_x1_0_doc_ori",
    "detection": "PP-OCRv6_medium_det",
    "recognition": "PP-OCRv6_medium_rec",
}
DOWNLOAD = ".venv-ocr/Scripts/python.exe src/scripts/pdf_paddle_worker.py --download"
DEVICE = "gpu:0"
# The orientation classifier resizes its input to 224 pixels; it was measured on ~100 DPI renders.
ORIENTATION_SIDE = 1200
GPU_MEMORY_MB = 6000


def model_dir(name: str) -> Path:
    # Paddle's own cache layout, so `--download` fills exactly the directories that are read.
    return CACHE / "official_models" / name


def configure() -> None:
    # Set before Paddle is imported: its caches stay in the project instead of the home folder,
    # and no model hoster is contacted to choose a download source.
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(CACHE)
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    # Paddle also creates ~/.cache/paddle and ~/.paddlex on import; this process gets a home
    # inside the cache folder, so nothing is written to the user's profile.
    home = CACHE / "home"
    home.mkdir(parents=True, exist_ok=True)
    os.environ["USERPROFILE"] = os.environ["HOME"] = str(home)
    # Paddle keeps every block it allocated for a new image size: unbounded, the worker reached
    # 10 GB in six pages. Under a cap it frees idle blocks instead, at no measured cost; a 300 DPI
    # page needed at most ~5 GB on the 2026-11-27 benchmark, so 6 GB leaves a margin.
    os.environ["FLAGS_gpu_memory_limit_mb"] = str(GPU_MEMORY_MB)


def download() -> int:
    configure()
    from paddleocr import DocImgOrientationClassification, PaddleOCR

    DocImgOrientationClassification(model_name=MODELS["orientation"], device="cpu")
    PaddleOCR(
        text_detection_model_name=MODELS["detection"],
        text_recognition_model_name=MODELS["recognition"],
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
    )
    for name in MODELS.values():
        print(model_dir(name), "ok" if model_dir(name).is_dir() else "MISSING")
    return 0


class Engine:
    def __init__(self) -> None:
        missing = [
            name for name in MODELS.values() if not (model_dir(name) / "inference.yml").is_file()
        ]
        if missing:
            raise RuntimeError(
                f"lipsesc modelele PaddleOCR {', '.join(missing)} din {CACHE}; "
                f"descarcă-le o dată cu: {DOWNLOAD}"
            )
        import paddle

        if not paddle.device.is_compiled_with_cuda() or paddle.device.cuda.device_count() < 1:
            raise RuntimeError(
                "PaddleOCR are nevoie de un GPU CUDA; pe CPU o pagină durează ~15 min"
            )
        from paddleocr import DocImgOrientationClassification, PaddleOCR

        self.classifier = DocImgOrientationClassification(
            model_name=MODELS["orientation"],
            model_dir=str(model_dir(MODELS["orientation"])),
            device=DEVICE,
        )
        # The page arrives already turned upright and straightened, so the pipeline's own
        # orientation, unwarping (worse on the benchmark) and text-line steps stay off.
        self.ocr = PaddleOCR(
            text_detection_model_name=MODELS["detection"],
            text_detection_model_dir=str(model_dir(MODELS["detection"])),
            text_recognition_model_name=MODELS["recognition"],
            text_recognition_model_dir=str(model_dir(MODELS["recognition"])),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=DEVICE,
        )

    def read(self, image) -> dict:
        """Classify the orientation, and recognize an upright page in the same request; a turned
        page is turned and straightened by the caller, then sent to `recognize`."""
        angle = self.orientation(image)
        return {"angle": angle} if angle else {"angle": 0, **self.recognize(image)}

    def orientation(self, image) -> int:
        import cv2

        height, width = image.shape[:2]
        scale = ORIENTATION_SIDE / max(height, width)
        if scale < 1:
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
        # The label is the counter-clockwise rotation that turns the image upright.
        result = next(iter(self.classifier.predict(image)))
        return int(result["label_names"][0])

    def recognize(self, image) -> dict:
        result = self.ocr.predict(image)[0]
        rows = [
            [str(text), [float(value) for value in box], float(score)]
            for text, box, score in zip(
                result["rec_texts"], result["rec_boxes"], result["rec_scores"]
            )
        ]
        return {"rows": rows}


def failure(exc: BaseException) -> dict:
    text = f"{type(exc).__name__}: {exc}"
    lowered = text.lower()
    memory = any(
        marker in lowered
        for marker in ("out of memory", "resourceexhausted", "cudaerrormemoryallocation")
    )
    return {"error": text[-2000:], "memory": memory}


def serve() -> int:
    # Paddle and its native libraries print to stdout; the protocol keeps a private copy of the
    # real stdout, and everything else written there goes to stderr.
    answers = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    requests = sys.stdin.buffer

    def answer(message: dict) -> None:
        answers.write(json.dumps(message).encode("ascii") + b"\n")
        answers.flush()

    configure()
    try:
        import numpy as np

        engine = Engine()
    except Exception as exc:
        answer(failure(exc))
        return 1
    answer({"ready": True})
    while header := requests.readline():
        try:
            request = json.loads(header)
            size, width, height = (int(request[key]) for key in ("size", "width", "height"))
            data = requests.read(size)
            if len(data) != size or size != width * height * 3:
                raise ValueError("imaginea primită este incompletă")
            if request["op"] not in {"read", "recognize"}:
                raise ValueError(f"operație necunoscută: {request['op']}")
            # Paddle expects BGR channel order.
            pixels = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)
            image = np.ascontiguousarray(pixels[:, :, ::-1])
            answer(getattr(engine, request["op"])(image))
        except Exception as exc:
            answer(failure(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(download() if sys.argv[1:] == ["--download"] else serve())
