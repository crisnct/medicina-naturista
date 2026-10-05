import importlib.util as u
import sys

print("python", sys.version.split()[0], sys.executable)
for name in [
    "torch",
    "transformers",
    "sentence_transformers",
    "openvino",
    "optimum",
    "psutil",
    "fastembed",
    "onnxruntime",
    "ctranslate2",
    "faiss",
]:
    print("  " + name.ljust(20), "installed" if u.find_spec(name) else "-")
