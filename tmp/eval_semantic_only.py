"""Temporary experiment: score = V only (P1, P2, L weights set to 0). Does not touch source."""
import sys
sys.path.insert(0, "scripts")
from backend.ai import search
search.WEIGHT_PRIMARY = 0
search.WEIGHT_SECONDARY = 0
search.WEIGHT_LEXICAL = 0
search.WEIGHT_SEMANTIC = 1
from scripts import evaluate_retrieval
evaluate_retrieval.main()
