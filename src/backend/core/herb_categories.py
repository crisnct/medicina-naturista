"""Catalog groups and ranking scopes, independent of taxonomy and matching names."""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, get_args

HerbCategory = Literal[
    "plante medicinale",
    "fructe",
    "legume",
    "cereale",
    "seminte",
    "uleiuri esentiale",
    "suplimente",
    "aminoacizi",
    "vitamine",
    "minerale",
    "produse apicole",
    "fibre, probiotice, prebiotice",
]
TopClarification = Literal["count", "category"]
HERB_CATEGORIES: tuple[HerbCategory, ...] = get_args(HerbCategory)
BOTANICAL_CATEGORY: HerbCategory = "plante medicinale"
BOTANICAL_CATEGORIES = frozenset((BOTANICAL_CATEGORY, "fructe", "legume", "cereale"))
PRODUCT_CATEGORIES = frozenset(HERB_CATEGORIES) - BOTANICAL_CATEGORIES
CATEGORY_LABELS = MappingProxyType(
    dict(
        zip(
            HERB_CATEGORIES,
            (
                "plante medicinale",
                "fructe",
                "legume",
                "cereale",
                "semințe",
                "uleiuri esențiale",
                "suplimente",
                "aminoacizi",
                "vitamine",
                "minerale",
                "produse apicole",
                "fibre, probiotice și prebiotice",
            ),
            strict=True,
        )
    )
)
# Whole category phrases only: one component never selects the combined group.
CATEGORY_ALIASES: MappingProxyType[HerbCategory, tuple[str, ...]] = MappingProxyType(
    {
        "plante medicinale": ("plante medicinale", "plantele medicinale"),
        "fructe": ("fructe", "fructele"),
        "legume": ("legume", "legumele"),
        "cereale": ("cereale", "cerealele"),
        "seminte": ("seminte", "semintele"),
        "uleiuri esentiale": ("uleiuri esentiale", "uleiurile esentiale"),
        "suplimente": (
            "suplimente",
            "suplimentele",
            "suplimente alimentare",
            "suplimentele alimentare",
        ),
        "aminoacizi": ("aminoacizi", "aminoacizii"),
        "vitamine": ("vitamine", "vitaminele"),
        "minerale": ("minerale", "mineralele"),
        "produse apicole": ("produse apicole", "produsele apicole"),
        "fibre, probiotice, prebiotice": (
            "fibre probiotice prebiotice",
            "fibre probiotice si prebiotice",
            "fibrele probioticele si prebioticele",
            "fibrele probioticele prebioticele",
        ),
    }
)
GLOBAL_TOP_LABEL = "produse naturiste — toate categoriile"
GLOBAL_TOP_ALIASES = frozenset(
    (
        "",
        "plante",
        "plantele",
        "general",
        "toate categoriile",
        "produse naturiste",
        "produsele naturiste",
        "plante si produse",
        "produse naturiste toate categoriile",
    )
)
