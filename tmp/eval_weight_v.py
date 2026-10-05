"""Temporary experiment: weight of V (semantic) in the full formula; source untouched."""
import os
from backend.ai import search
search.WEIGHT_SEMANTIC = int(os.environ["WEIGHT_V"])
from scripts import evaluate_retrieval
evaluate_retrieval.main()
