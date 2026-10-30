"""Catalog groups and ranking scopes, independent of taxonomy and matching names."""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, get_args

from backend.core.texts import tr

HerbCategory = Literal[
    "plante medicinale",
    "fructe",
    "legume",
    "cereale",
    "seminte",
    "uleiuri esentiale",
    "uleiuri",
    "suplimente",
    "aminoacizi",
    "vitamine",
    "minerale",
]
TopClarification = Literal["count", "category", "condition"]
HERB_CATEGORIES: tuple[HerbCategory, ...] = get_args(HerbCategory)
BOTANICAL_CATEGORY: HerbCategory = "plante medicinale"
BOTANICAL_CATEGORIES = frozenset((BOTANICAL_CATEGORY, "fructe", "legume", "cereale"))
PRODUCT_CATEGORIES = frozenset(HERB_CATEGORIES) - BOTANICAL_CATEGORIES


def category_labels() -> MappingProxyType[HerbCategory, str]:
    return MappingProxyType(
        dict(
            zip(
                HERB_CATEGORIES,
                (
                    tr("conversation.category_medicinal_plants"),
                    tr("conversation.category_fruit"),
                    tr("conversation.category_vegetables"),
                    tr("conversation.category_cereals"),
                    tr("conversation.category_seeds"),
                    tr("conversation.category_essential_oils"),
                    tr("conversation.category_oils"),
                    tr("conversation.category_supplements"),
                    tr("conversation.category_amino_acids"),
                    tr("conversation.category_vitamins"),
                    tr("conversation.category_minerals"),
                ),
                strict=True,
            )
        )
    )


# Merged product scopes resolve to supplements, which owns their catalog entries.
CATEGORY_ALIASES: MappingProxyType[HerbCategory, tuple[str, ...]] = MappingProxyType(
    {
        "plante medicinale": (
            "medicinal herbs",
            "medicinal plants",
            "plante medicinale",
            "plantele medicinale",
        ),
        "fructe": ("fruits", "fruit", "fructe", "fructele"),
        "legume": ("vegetables", "legume", "legumele"),
        "cereale": ("cereals", "grains", "cereale", "cerealele"),
        "seminte": ("seeds", "seminte", "semintele"),
        "uleiuri esentiale": ("essential oils", "uleiuri esentiale", "uleiurile esentiale"),
        "uleiuri": (
            "oils",
            "vegetable oils",
            "uleiuri",
            "uleiurile",
            "uleiuri vegetale",
            "uleiurile vegetale",
        ),
        "suplimente": (
            "supplements",
            "dietary supplements",
            "bee products",
            "fiber",
            "fibre",
            "probiotics",
            "prebiotics",
            "suplimente",
            "suplimentele",
            "suplimente alimentare",
            "suplimentele alimentare",
            "produse apicole",
            "produsele apicole",
            "fibre",
            "fibrele",
            "probiotice",
            "probioticele",
            "prebiotice",
            "prebioticele",
            "fibre probiotice prebiotice",
            "fibre probiotice si prebiotice",
            "fibrele probioticele si prebioticele",
            "fibrele probioticele prebioticele",
        ),
        "aminoacizi": ("amino acids", "aminoacizi", "aminoacizii"),
        "vitamine": ("vitamins", "vitamine", "vitaminele"),
        "minerale": ("minerals", "minerale", "mineralele"),
    }
)


def global_top_label() -> str:
    return tr("conversation.global_top_label")


GLOBAL_TOP_ALIASES = frozenset(
    (
        "",
        "plante",
        "plantele",
        "general",
        "toate categoriile",
        "all categories",
        "natural products",
        "herbs",
        "plants",
        "produse naturiste",
        "produsele naturiste",
        "plante si produse",
        "produse naturiste toate categoriile",
    )
)
