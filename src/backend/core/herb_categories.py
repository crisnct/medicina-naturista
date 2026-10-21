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
    "medicamente",
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
                    tr("conversation.category_medicines"),
                    tr("conversation.category_amino_acids"),
                    tr("conversation.category_vitamins"),
                    tr("conversation.category_minerals"),
                    tr("conversation.category_bee_products"),
                    tr("conversation.category_fibre_probiotics_prebiotics"),
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
        "uleiuri": ("uleiuri", "uleiurile", "uleiuri vegetale", "uleiurile vegetale"),
        "suplimente": (
            "suplimente",
            "suplimentele",
            "suplimente alimentare",
            "suplimentele alimentare",
        ),
        "aminoacizi": ("aminoacizi", "aminoacizii"),
        "medicamente": ("medicamente", "medicamentele"),
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


def global_top_label() -> str:
    return tr("conversation.global_top_label")


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
