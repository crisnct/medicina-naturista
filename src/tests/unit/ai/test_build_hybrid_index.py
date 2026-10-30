from __future__ import annotations

import dataclasses
import io
import unittest
from contextlib import redirect_stdout

import numpy as np

from backend.ai import categories
from backend.ai.embedding_model import EmbeddingProfile, get_profile
from scripts import build_hybrid_index as builder

QWEN = get_profile(builder.DEFAULT_MODEL)
# A second, narrower model that only exists in the tests, to exercise a model change.
OTHER = EmbeddingProfile("test/other-model", 64, "{text}", "{text}", 1400, 240)


def make_chunk(index: int, text: str = "text") -> builder.Chunk:
    return builder.Chunk(
        source_relative_path="document.md",
        source_absolute_path="C:/documents/document.md",
        source_sha256="source-hash",
        line_start=1,
        line_end=1,
        heading="Titlu",
        text=text,
        text_sha256=f"text-hash-{index}",
        char_count=len(text),
    )


class FakeClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class FakeEmbeddingModel:
    def __init__(self, count: int, *, fail_after: int | None = None) -> None:
        self.count = count
        self.fail_after = fail_after

    def embed(self, documents, batch_size: int, parallel):
        inputs = list(documents)
        if len(inputs) != self.count:
            raise AssertionError(f"Expected {self.count} inputs, received {len(inputs)}")
        for index in range(self.count):
            if self.fail_after is not None and index == self.fail_after:
                raise RuntimeError("embedding failed")
            vector = np.zeros(QWEN.dimension, dtype=np.float32)
            vector[index % QWEN.dimension] = 1.0
            yield vector


# Return unit-normalized deterministic embeddings, standing in for the real
# ONNX model in tests that only care about the sync/DB-write behaviour.
def fake_embed(_model, chunks, _batch_size, profile, *, gpu_usage=None):
    vectors = np.ones((len(chunks), profile.dimension), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors


class ChunkingTests(unittest.TestCase):
    def test_normalize_text_preserves_composed_romanian_diacritics(self):
        decomposed = "s\u0326i t\u0326erapie\r\n"

        self.assertEqual(builder.normalize_text(decomposed), "și țerapie\n")
        from dataclasses import replace
        from unittest.mock import patch

        from backend.ai.herb_association_classification import (
            cache_key,
            group_fragment_works,
            group_works,
            model_digest,
            pack_batches,
            quotation_spans,
            relation_id,
            response_schema,
            semantic_config,
            serialize_batch,
            validate_cached,
            validate_response,
        )
        from backend.ai.herb_association_rules import (
            Decision,
            IndexedPassage,
            classify_rule,
            combine_decisions,
            content_hash,
            extract_units,
            pair_state,
            scoped_warning,
            source_context,
        )
        from backend.config import Settings

        names = (("menta", (1,)), ("musetel", (2,)))
        conditions = (("gastrita", (10,)), ("diabet", (11,)))
        passage = IndexedPassage(
            1,
            "synthetic.md",
            "source",
            "chunk",
            "Gastrita",
            "# Gastrita\n## Alimente recomandate\n- menta\n## Contraindicatii\n- musetel\n",
            ("Gastrita",),
        )
        units = extract_units(passage, names, conditions)
        self.assertEqual(
            [classify_rule(u, u.candidates[0]).label for u in units], ["positive", "caution"]
        )
        self.assertEqual(
            units[0].text[units[0].candidates[0].mention[0] : units[0].candidates[0].mention[1]],
            "menta",
        )
        self.assertEqual(pair_state(["positive", "unclear", "positive"]), "positive")
        self.assertEqual(pair_state(["positive", "caution"]), "mixed")
        self.assertEqual(pair_state(["mixed"]), "mixed")
        self.assertEqual(pair_state(["unclear"]), "unclear")
        self.assertEqual(pair_state(["caution", "caution"]), "caution")
        ambiguous = extract_units(
            replace(
                passage, text="# Gastrita\nSe recomanda menta, dar musetel este contraindicat.\n"
            ),
            names,
            conditions,
        )[0]
        self.assertTrue(all(classify_rule(ambiguous, c) is None for c in ambiguous.candidates))
        adverse_list = extract_units(
            replace(
                passage,
                text="# Gastrita\nAlimente recomandate: menta. Musetel agraveaza gastrita.\n",
            ),
            names,
            conditions,
        )[0]
        self.assertTrue(
            all(classify_rule(adverse_list, c) is None for c in adverse_list.candidates)
        )
        shared_name = extract_units(
            replace(passage, text="# Gastrita\nSe recomanda menta.\n"),
            (("menta", (1, 2)),),
            conditions,
        )[0]
        self.assertTrue(
            all(
                classify_rule(shared_name, c)
                == Decision("unclear", "rule", "ambiguous_identity_v2")
                for c in shared_name.candidates
            )
        )
        other = extract_units(
            replace(passage, text="# Gastrita\nMenta este contraindicata pentru diabet.\n"),
            names,
            conditions,
        )[0]
        self.assertIsNone(classify_rule(other, other.candidates[0]))
        table = extract_units(
            replace(passage, text="# Gastrita\n| menta | recomandari neclare |\n"),
            names,
            conditions,
        )[0]
        self.assertIsNone(classify_rule(table, table.candidates[0]))
        fallback = extract_units(replace(passage, text="Menta se recomanda."), names, conditions)[0]
        self.assertIsNone(classify_rule(fallback, fallback.candidates[0]))
        misattributed = replace(
            fallback,
            certain_context=True,
            scope_conditions=(10,),
            headings=("Recomandari pentru diabet",),
        )
        self.assertIsNone(classify_rule(misattributed, misattributed.candidates[0]))
        ingredient = extract_units(
            replace(passage, text="# Gastrita\n28gde frunze de menta\n"), names, conditions
        )[0]
        self.assertIsNone(classify_rule(ingredient, ingredient.candidates[0]))
        book_scope = extract_units(
            replace(
                passage,
                heading="Tratamente si recomandari generale > Gastrita. Tratament",
                text="- gemoderivat de menta: 1 doza sau 2ml pe zi timp de maxim o luna.\n",
            ),
            names,
            conditions,
        )[0]
        self.assertIsNone(classify_rule(book_scope, book_scope.candidates[0]))
        self.assertEqual(book_scope.text, book_scope.passage.text)
        explicit_book_scope = replace(
            book_scope, headings=("Suplimente naturiste recomandate pentru Gastrita",)
        )
        self.assertIsNone(classify_rule(explicit_book_scope, explicit_book_scope.candidates[0]))
        qualified = extract_units(
            replace(passage, text="# Gastrita\nSe recomanda menta creata.\n"),
            (*names, ("menta creata", (3,))),
            conditions,
        )[0]
        self.assertEqual(classify_rule(qualified, qualified.candidates[0]).label, "unclear")
        self.assertEqual(len(qualified.candidates), 2)
        salad = extract_units(
            replace(passage, text="# Gastrita\nMancati salata de menta.\n"),
            (*names, ("salata", (3,))),
            conditions,
        )[0]
        self.assertEqual(classify_rule(salad, salad.candidates[0]).label, "unclear")
        aliased_scope = extract_units(
            replace(passage, primary=("Gastropatie",), text="# Gastrita\nLuati menta.\n"),
            names,
            conditions,
            canonical_conditions={"gastropatie": 10},
        )[0]
        self.assertEqual(
            classify_rule(aliased_scope, aliased_scope.candidates[0]).label, "positive"
        )
        partial_alias = extract_units(
            replace(
                passage,
                primary=("Gastropatie",),
                text="# Gastrita secundara\nLuati menta.\n",
            ),
            names,
            conditions,
            canonical_conditions={"gastropatie": 10},
        )[0]
        self.assertIsNone(classify_rule(partial_alias, partial_alias.candidates[0]))
        recipe = extract_units(
            replace(
                passage,
                text="# Gastrita\nSe combina menta si musetel. Se bea o cana zilnic.\n",
            ),
            names,
            conditions,
        )[0]
        self.assertTrue(
            all(classify_rule(recipe, c).label == "positive" for c in recipe.candidates)
        )
        for text in ("Menta 100mg zilnic.", "- Ceai de menta", "1 parte menta"):
            named = extract_units(
                replace(passage, text="# Gastrita\n" + text + "\n"), names, conditions
            )[0]
            self.assertIsNone(classify_rule(named, named.candidates[0]))
        banned_ingredient = extract_units(
            replace(passage, text="# Gastrita\n## Contraindicatii\n- menta\n"),
            names,
            conditions,
        )[0]
        self.assertEqual(
            classify_rule(banned_ingredient, banned_ingredient.candidates[0]).label, "caution"
        )
        administered = extract_units(
            replace(passage, text="# Gastrita\nLuati 28 g de menta pentru gastrita.\n"),
            names,
            conditions,
        )[0]
        self.assertIsNone(classify_rule(administered, administered.candidates[0]))
        composition = extract_units(
            replace(
                passage, text="# Gastrita\nAlimente cu continut mare de fier sunt menta, musetel.\n"
            ),
            names,
            conditions,
        )[0]
        self.assertTrue(
            all(classify_rule(composition, c).label == "unclear" for c in composition.candidates)
        )
        parenthetical = extract_units(
            replace(
                passage,
                text="# Gastrita\nAlimente cu continut mare de fier sunt menta (mancati musetel).\n",
            ),
            names,
            conditions,
        )[0]
        self.assertIsNone(classify_rule(parenthetical, parenthetical.candidates[-1]))
        fever = extract_units(
            replace(passage, primary=("Febra",), text="# Febra fanului\nConsumati menta.\n"),
            names,
            (("febra", (10,)),),
        )[0]
        self.assertEqual(classify_rule(fever, fever.candidates[0]).label, "unclear")
        actual_fever = extract_units(
            replace(
                passage,
                primary=("Febra",),
                text="# Febra fanului\nMenta se recomanda pentru febra.\n",
            ),
            names,
            (("febra", (10,)),),
        )[0]
        self.assertEqual(classify_rule(actual_fever, actual_fever.candidates[0]).label, "positive")
        negation = extract_units(
            replace(passage, text="# Gastrita\nMenta nu se recomanda.\n"), names, conditions
        )[0]
        self.assertEqual(classify_rule(negation, negation.candidates[0]).label, "caution")
        avoidance = extract_units(
            replace(passage, text="# Gastrita\nSe recomanda evitarea menta.\n"), names, conditions
        )[0]
        self.assertEqual(classify_rule(avoidance, avoidance.candidates[0]).label, "caution")
        pregnancy = extract_units(
            replace(passage, text="# Gastrita\nMenta este contraindicata in sarcina.\n"),
            names,
            conditions,
        )[0]
        self.assertIsNone(classify_rule(pregnancy, pregnancy.candidates[0]))
        scoped = extract_units(
            replace(
                passage,
                text="# Gastrita\n## Diabet\nSe recomanda menta.\n",
                primary=("Gastrita", "Diabet"),
            ),
            names,
            conditions,
        )
        self.assertEqual({c.condition_id for u in scoped for c in u.candidates}, {11})
        self.assertEqual(
            extract_units(
                replace(passage, text="# Gastrita\n## Diabet\nSe recomanda menta.\n"),
                names,
                conditions,
            ),
            (),
        )
        self.assertEqual(extract_units(replace(passage, primary=()), names, conditions), ())
        canonical_only = extract_units(
            passage, names, (("gastrita", (10, 11)),), canonical_conditions={"gastrita": 10}
        )
        self.assertEqual({c.condition_id for u in canonical_only for c in u.candidates}, {10})
        self.assertEqual(
            extract_units(replace(passage, text="# Gastrita\nmentolat"), names, conditions), ()
        )

        from functools import partial

        from backend.ai.herb_association_scope import LocalConditionScope

        scope_catalog = LocalConditionScope({10: "Gastrita", 11: "Diabet"}, {})
        validate_response = partial(validate_response, scope_catalog=scope_catalog)
        model_source = extract_units(
            replace(passage, text="# Gastrita\nMenta este mentionata."), names, conditions
        )[0]
        work = group_fragment_works(
            [(model_source, model_source.candidates[0])], {10: "Gastrita", 11: "Diabet"}
        )[0].work
        identifier = relation_id(work)
        text_with_repetition = "Menta.\n" * 200 + "x" * 700
        spans = quotation_spans(text_with_repetition)
        self.assertEqual(
            "".join(text_with_repetition[a:b] for a, b in spans.values()), text_with_repetition
        )
        self.assertTrue(all(0 < b - a <= 1000 for a, b in spans.values()))
        wrapped = "Menta\neste mentionata\npentru gastrita.\nPrecautii: consultati\nmedicul."
        self.assertEqual(len(quotation_spans(wrapped)), 1)
        self.assertEqual(
            "".join(wrapped[a:b] for a, b in quotation_spans(wrapped).values()), wrapped
        )
        valid = {
            "relations": {
                "r0": {
                    "local_condition": "Gastrita",
                    "recommendation": True,
                    "prohibition": False,
                }
            }
        }
        self.assertEqual(validate_response(valid, [work])[identifier].label, "positive")
        from backend.ai.herb_caution_projection import (
            corroborate_projection,
            list_prohibition,
            local_projection,
            model_projections,
        )

        both = {"relations": {"r0": {**valid["relations"]["r0"], "prohibition": True}}}
        dual_decisions = validate_response(both, [work])
        self.assertEqual(dual_decisions[identifier].label, "positive")
        warning = model_projections(both, [work], dual_decisions)[identifier]
        self.assertEqual(warning.warning_kind, "prohibition")
        self.assertTrue(warning.has_recommendation)
        self.assertEqual(
            corroborate_projection(
                warning, local_projection(((negation, negation.candidates[0]),))
            ).warning_kind,
            "prohibition",
        )
        unrelated_bath = extract_units(
            replace(
                passage,
                text="# Gastrita\nMenta este utila pentru recuperarea energiei.\n\nBaia fierbinte este contraindicata persoanelor cu diabet.\n",
            ),
            names,
            conditions,
        )
        bath_group = group_fragment_works(
            [(unit, candidate) for unit in unrelated_bath for candidate in unit.candidates],
            {10: "Gastrita", 11: "Diabet"},
        )[0]
        self.assertEqual(
            corroborate_projection(warning, local_projection(bath_group.originals)).warning_kind,
            "unknown",
        )
        wrapped_avoidance = extract_units(
            replace(passage, text="# Gastrita\nQ Nu consumati produse ca oua,\nmenta, zahar.\n"),
            names,
            (*conditions, ("zahar", (11,))),
        )
        avoidance_group = group_fragment_works(
            [(unit, candidate) for unit in wrapped_avoidance for candidate in unit.candidates],
            {10: "Gastrita", 11: "Diabet"},
        )[0]
        self.assertEqual(
            list_prohibition(
                avoidance_group.work, scope_catalog=scope_catalog, condition_name="Gastrita"
            ).warning_kind,
            "prohibition",
        )
        self.assertEqual(
            local_projection(((units[1], units[1].candidates[0]),)).warning_kind, "prohibition"
        )
        scoped_work = group_fragment_works(
            [(scoped[0], scoped[0].candidates[0])], {10: "Gastrita", 11: "Diabet"}
        )[0].work
        borrowed = (scoped_work[0], replace(scoped_work[1], condition_id=10))
        self.assertEqual(next(iter(validate_response(valid, [borrowed]).values())).label, "unclear")
        local_diabetes = {
            "relations": {
                "r0": {
                    **valid["relations"]["r0"],
                    "local_condition": "Diabet",
                }
            }
        }
        self.assertEqual(
            next(iter(validate_response(local_diabetes, [scoped_work]).values())).label, "positive"
        )
        for raw in (
            None,
            {},
            {"relations": []},
            {"relations": {**valid["relations"], "extra": valid["relations"]["r0"]}},
            {"relations": {"invented": [1]}},
            {"relations": {"r0": [1, "absent"]}},
            {"relations": {"r0": [3]}},
            {"relations": {"r0": [4]}},
        ):
            with self.assertRaises(ValueError):
                validate_response(raw, [work])
        unclear = {
            "relations": {
                "r0": {
                    "local_condition": "",
                    "recommendation": False,
                    "prohibition": False,
                }
            }
        }
        repeated_mixed = {"relations": {"r0": [3, "a", "a"]}}
        with self.assertRaisesRegex(ValueError, "POSITIVE_INVALID_RELATION"):
            validate_response(repeated_mixed, [work])
        self.assertEqual(
            validate_response(unclear, [work])[identifier], Decision("unclear", "model", "")
        )
        self.assertEqual(
            model_projections(unclear, [work], validate_response(unclear, [work]))[
                identifier
            ].warning_kind,
            "none",
        )
        config = Settings()
        semantic = semantic_config(config)
        self.assertEqual(
            semantic,
            semantic_config(
                replace(config, herb_association_ai_base="http://host.docker.internal:11434/v1")
            ),
        )
        self.assertEqual(
            cache_key(work, semantic, "a"),
            cache_key(
                work, semantic_config(replace(config, herb_association_ai_timeout_seconds=60)), "a"
            ),
        )
        self.assertNotEqual(cache_key(work, semantic, "a"), cache_key(work, semantic, "b"))
        self.assertNotEqual(
            cache_key(work, semantic, "a"), cache_key(work, {**semantic, "prompt": "changed"}, "a")
        )
        self.assertEqual(
            cache_key(work, semantic, "a"),
            cache_key(
                work,
                {
                    **semantic,
                    "schema": 99,
                    "transport": "different",
                    "transport_policy": "different implementation",
                    "rules": 9,
                    "rules_policy": "new",
                },
                "a",
            ),
        )
        repeated = extract_units(
            replace(passage, text="# Gastrita\nMenta este mentionata. Menta apare din nou.\n"),
            names,
            conditions,
        )[0]
        originals = [(repeated, c) for c in repeated.candidates]
        grouped = group_works(originals)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(len(grouped[0][0][1].mentions), 2)
        self.assertEqual(grouped[0][1], tuple(originals))
        self.assertNotEqual(
            cache_key(grouped[0][0], semantic, "a"), cache_key(originals[0], semantic, "a")
        )
        import json

        isolated = [work, grouped[0][0]]
        synonyms = {10: ("Gastropatie", "gastritis", "inflamatie gastrica")}
        payload = json.loads(
            serialize_batch(isolated, {1: "menta"}, {10: "Gastrita"}, condition_synonyms=synonyms)
        )
        self.assertTrue(
            all(c["condition_synonyms"] == list(synonyms[10]) for c in payload["candidates"])
        )
        self.assertNotEqual(
            cache_key(work, {**semantic, "condition_synonyms": synonyms[10]}, "a"),
            cache_key(work, {**semantic, "condition_synonyms": ()}, "a"),
        )
        schema = response_schema(payload)
        self.assertEqual(
            set(schema["properties"]["relations"]["properties"]["r1"]["properties"]),
            {"local_condition", "recommendation", "prohibition"},
        )
        self.assertEqual(payload["units"]["u1"]["text"], isolated[1][0].text)
        self.assertNotIn("segments", payload["units"]["u1"])
        for candidate in payload["candidates"]:
            original = payload["units"][candidate["unit"]]["text"]
            self.assertEqual(
                candidate["mention_texts"], [original[a:b] for a, b in candidate["mentions"]]
            )
        with self.assertRaisesRegex(ValueError, "POSITIVE_INVALID_RELATION"):
            validate_response(
                {
                    "relations": {
                        "r0": {**valid["relations"]["r0"], "evidence_id": "b"},
                        "r1": unclear["relations"]["r0"],
                    }
                },
                isolated,
            )
        nutrient = extract_units(
            replace(
                passage,
                text="# Gastrita\n## NUTRIENTI\nMenta 100 mg zilnic. Musetel 100 mg zilnic.\n",
            ),
            names,
            conditions,
        )[0]
        nutrient_works = [w for w, m in group_works([(nutrient, c) for c in nutrient.candidates])]
        self.assertEqual(
            len(pack_batches(nutrient_works, config, {1: "menta", 2: "musetel"}, {10: "Gastrita"})),
            1,
        )
        for text in (
            "Se adauga menta dupa gust si se bea preparatul.",
            "Se foloseste rachiu de menta pentru macerare.",
            "Nivelul scazut de menta a fost asociat gastritei.",
            "Se ia musetel cu 100 mg de menta pentru o absorbtie mai buna.",
        ):
            described = extract_units(
                replace(passage, text="# Gastrita\n" + text + "\n"), names, conditions
            )[0]
            mint = next(c for c in described.candidates if c.herb_id == 1)
            self.assertEqual(classify_rule(described, mint).label, "unclear")
        doses_only = extract_units(
            replace(
                passage,
                text="# Gastrita\n| Coloana 1 | Coloana 2 |\n| --- | --- |\n| menta o capsula | musetel un comprimat |\n",
            ),
            names,
            conditions,
        )[-1]
        self.assertTrue(all(classify_rule(doses_only, c) is None for c in doses_only.candidates))
        validate_cached(Decision("positive", "model", "", ((0, 5),)), work)
        with self.assertRaisesRegex(ValueError, "POSITIVE_INVALID_CACHE"):
            validate_cached(Decision("positive", "model", "", ((0, len(work[0].text) + 1),)), work)
        listed = extract_units(
            replace(passage, text="# Gastrita\nAlimente recomandate:\n\n- menta, musetel\n"),
            names,
            conditions,
        )[-1]
        self.assertTrue(listed.scope)
        self.assertTrue(
            all(classify_rule(listed, c).label == "positive" for c in listed.candidates)
        )
        column = extract_units(
            replace(
                passage,
                text="# Gastrita\n| Alimente recomandate | Alimente interzise |\n| --- | --- |\n| menta | musetel |\n",
            ),
            names,
            conditions,
        )[-1]
        self.assertIsNotNone(column.table_header)
        self.assertEqual(
            [classify_rule(column, c).label for c in column.candidates], ["positive", "caution"]
        )
        separated = extract_units(
            replace(
                passage,
                text="# Gastrita\n| Alimente recomandate | Alimente interzise |\n| --- | --- |\n| menta | musetel |\n\n| menta | musetel |\n",
            ),
            names,
            conditions,
        )[-1]
        self.assertIsNone(separated.table_header)
        ocr = extract_units(
            replace(
                passage,
                text="# Gastrita\nSUPLIMENT DOZA RECOMANDATA OBSERVATII\nMenta 100 mg zilnic.\n\nMusetel 100 mg zilnic.\n\nPlante\nMenta este descrisa.\n",
            ),
            names,
            conditions,
        )
        self.assertIn("DOZA RECOMANDATA", source_context(ocr[1])["table_header"])
        self.assertEqual(classify_rule(ocr[1], ocr[1].candidates[0]).label, "positive")
        self.assertIsNone(source_context(ocr[-1])["table_header"])
        self.assertIsNone(classify_rule(ocr[-1], ocr[-1].candidates[0]))
        inherited = extract_units(
            replace(
                passage,
                text="# Recomandari pentru gastrita\n## Uz intern\n- Ceai/tinctura de menta\n",
            ),
            names,
            conditions,
        )[-1]
        self.assertEqual(classify_rule(inherited, inherited.candidates[0]).label, "positive")
        foreign_intro = extract_units(
            replace(passage, text="# Gastrita\nAlimente recomandate pentru diabet:\n\n- menta\n"),
            names,
            conditions,
        )[-1]
        self.assertIsNone(classify_rule(foreign_intro, foreign_intro.candidates[0]))
        self.assertEqual(len(pack_batches([work], config, {1: "menta"}, {10: "Gastrita"})), 1)
        seven = [
            (
                replace(repeated, passage=replace(repeated.passage, chunk_id=number)),
                repeated.candidates[0],
            )
            for number in range(20, 27)
        ]
        self.assertEqual(
            len(pack_batches(seven, config, {1: "menta"}, {10: "Gastrita"}, prompt="synthetic")),
            2,
        )
        source_limited = pack_batches(
            seven,
            replace(
                config,
                herb_association_ai_max_passage_chars=len(repeated.text) * 2,
                herb_association_ai_max_units=2,
            ),
            {1: "menta"},
            {10: "Gastrita"},
            prompt="synthetic",
        )
        self.assertEqual(sum(len(batch) for batch in source_limited), 7)
        self.assertTrue(all(len(batch) <= 2 for batch in source_limited))
        long_text = ("Menta. " * 800).strip()
        long_unit = replace(
            fallback,
            passage=replace(fallback.passage, text=long_text),
            start=0,
            end=len(long_text),
        )
        long_work = (long_unit, long_unit.candidates[0])
        self.assertGreater(len(long_text), 5000)
        self.assertEqual(len(pack_batches([long_work], config, {1: "menta"}, {10: "Gastrita"})), 1)
        long_payload = json.loads(serialize_batch([long_work], {1: "menta"}, {10: "Gastrita"}))
        self.assertEqual(long_payload["units"]["u0"]["text"], long_text)
        self.assertNotIn("segments", long_payload["units"]["u0"])
        seventh_text = "Menta. " * 1000
        seventh_unit = replace(
            long_unit, passage=replace(long_unit.passage, text=seventh_text), end=len(seventh_text)
        )
        seventh_work = (seventh_unit, seventh_unit.candidates[0])
        isolated = pack_batches([seventh_work, seven[0]], config, {1: "menta"}, {10: "Gastrita"})
        self.assertEqual(len(isolated), 2)
        oversized_payload = json.loads(serialize_batch(isolated[0], {1: "menta"}, {10: "Gastrita"}))
        self.assertEqual(oversized_payload["units"]["u0"]["text"], seventh_text)
        self.assertNotIn("segments", oversized_payload["units"]["u0"])
        with self.assertRaisesRegex(ValueError, "POSITIVE_UNIT_TOO_LARGE"):
            pack_batches(
                [seventh_work],
                replace(config, herb_association_ai_max_input_chars=len(seventh_text)),
                {1: "menta"},
                {10: "Gastrita"},
            )
        grouped_repeated = grouped[0][0]
        self.assertEqual(
            len(
                pack_batches(
                    [grouped_repeated],
                    replace(config, herb_association_ai_max_passage_chars=len(repeated.text)),
                    {1: "menta"},
                    {10: "Gastrita"},
                    prompt="synthetic",
                )
            ),
            1,
        )
        self.assertTrue(
            all(
                len(batch) <= 3
                for batch in pack_batches(
                    seven,
                    replace(config, herb_association_ai_max_pairs=3),
                    {1: "menta"},
                    {10: "Gastrita"},
                )
            )
        )
        with self.assertRaisesRegex(ValueError, "POSITIVE_UNIT_TOO_LARGE"):
            pack_batches(
                [work],
                replace(config, herb_association_ai_max_input_chars=10),
                {1: "menta"},
                {10: "Gastrita"},
            )
        with patch("backend.ai.herb_association_classification.httpx.Client") as http:
            response = http.return_value.__enter__.return_value.get.return_value
            response.json.return_value = {"models": []}
            with self.assertRaisesRegex(ValueError, "POSITIVE_MODEL_UNAVAILABLE"):
                model_digest(config)
            http.return_value.__enter__.return_value.get.assert_called_once()
        from unittest.mock import Mock

        from backend.ai.client import AIUnavailable
        from backend.ai.herb_positive_repository import PositiveRepository, Snapshot
        from scripts.positive_herb_ranking import run_positive_ranking

        repository = Mock(spec=PositiveRepository)
        repository.read_snapshot.return_value = Snapshot(
            {}, None, (1,), {1: "menta"}, {10: "Gastrita"}, (work,)
        )
        repository.cached.return_value = {}
        repository.create_run.return_value = {"status": "preparing"}
        client = Mock()
        output = io.StringIO()
        with (
            patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
            patch("scripts.positive_herb_ranking.make_client", return_value=client),
            redirect_stdout(output),
        ):
            client.complete_json.side_effect = TimeoutError("synthetic timeout")
            with self.assertRaises(TimeoutError):
                run_positive_ranking(config, repository=repository)
            repository.finish.assert_not_called()
            repository.save_cache.assert_not_called()
            repository.publish.assert_not_called()
            client.complete_json.assert_called_once()
            client.complete_json.reset_mock()
            client.complete_json.side_effect = AIUnavailable(
                "synthetic incomplete", reason="output_limit"
            )
            with self.assertRaises(AIUnavailable):
                run_positive_ranking(config, repository=repository)
            repository.finish.assert_not_called()
            repository.save_cache.assert_not_called()
            client.complete_json.assert_called_once()
            client.complete_json.reset_mock()
            repository.admit_request.side_effect = ValueError("POSITIVE_REQUEST_LIMIT")
            with self.assertRaisesRegex(ValueError, "POSITIVE_REQUEST_LIMIT"):
                run_positive_ranking(config, repository=repository)
            client.complete_json.assert_not_called()
            repository.finish.assert_not_called()
            self.assertEqual(json.loads(output.getvalue().splitlines()[-1])["requests"], 0)
            self.assertEqual(
                json.loads(output.getvalue().splitlines()[-1])["ai_requests_sent_total"], 0
            )
        self.assertNotIn("Menta", output.getvalue())
        self.assertNotIn("synthetic timeout", output.getvalue())
        consultation = extract_units(
            replace(
                passage,
                text="# Gastrita\nMenta ajuta in gastrita. Precautii: Daca aveti gastrita, "
                "consultati medicul inainte de a lua menta.\n",
            ),
            names,
            conditions,
        )[0]
        warning_work = group_works([(consultation, c) for c in consultation.candidates])[0][0]
        warning = scoped_warning(*warning_work)
        self.assertIsNotNone(warning)
        self.assertEqual(warning.label, "caution")
        self.assertEqual(
            combine_decisions([Decision("positive", "model", "", ((0, 22),)), warning]).label,
            "mixed",
        )
        foreign_warning = extract_units(
            replace(
                passage,
                text="# Gastrita\nMenta ajuta in gastrita. Precautii: Daca aveti diabet, "
                "consultati medicul inainte de a lua menta.\n",
            ),
            names,
            conditions,
        )[0]
        self.assertIsNone(scoped_warning(foreign_warning, foreign_warning.candidates[-1]))
        avoided = extract_units(
            replace(passage, text="# Gastrita\nQ Eliminati din dieta menta.\n"), names, conditions
        )[0]
        self.assertEqual(scoped_warning(avoided, avoided.candidates[0]).label, "caution")
        supervised = extract_units(
            replace(passage, text="# Gastrita\nLuati menta numai sub supraveghere medicala.\n"),
            names,
            conditions,
        )[0]
        self.assertEqual(scoped_warning(supervised, supervised.candidates[0]).label, "caution")
        dose_warning = extract_units(
            replace(passage, text="# Gastrita\nNu luati mai mult de 600 mg de menta zilnic.\n"),
            names,
            conditions,
        )[0]
        self.assertIsNone(scoped_warning(dose_warning, dose_warning.candidates[0]))
        inflected = extract_units(
            replace(
                passage,
                text="# Gastrita\nSe recomanda musetel. Urmati sfatul medicului privind includerea musetelului in dieta.\n",
            ),
            names,
            conditions,
        )[0]
        self.assertEqual(scoped_warning(inflected, inflected.candidates[0]).label, "caution")
        negated_consultation = extract_units(
            replace(
                passage,
                text="# Gastrita\nDaca aveti gastrita, nu consultati medicul inainte de a lua menta.\n",
            ),
            names,
            conditions,
        )[0]
        self.assertIsNone(scoped_warning(negated_consultation, negated_consultation.candidates[0]))
        collective = extract_units(
            replace(
                passage,
                text="# Gastrita\nQ Evitati suplimentele pentru gastrita.\nQ Menta ajuta in gastrita.\n",
            ),
            names,
            conditions,
            herb_categories={1: "suplimente"},
        )[0]
        self.assertEqual(scoped_warning(collective, collective.candidates[0]).label, "caution")
        self.assertIsNone(
            scoped_warning(
                replace(collective, product_categories=((1, "plante_medicinale"),)),
                collective.candidates[0],
            )
        )
        for text, alias in (
            ("Ciroza hepatica este mentionata.", "hepatica"),
            ("Se recomanda miere de salcam pentru gastrita.", "salcam"),
        ):
            collision = extract_units(
                replace(passage, text=f"# Gastrita\n{text}\n"), ((alias, (1,)),), conditions
            )[0]
            self.assertEqual(classify_rule(collision, collision.candidates[0]).label, "unclear")
        repository.read_snapshot.return_value = Snapshot(
            {},
            None,
            (1,),
            {1: "menta"},
            {10: "Gastrita"},
            tuple((consultation, c) for c in consultation.candidates),
        )
        repository.admit_request.side_effect = None
        client.complete_json.side_effect = None
        client.complete_json.return_value = valid
        with (
            patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
            patch("scripts.positive_herb_ranking.make_client", return_value=client),
            redirect_stdout(output),
        ):
            result = run_positive_ranking(config, repository=repository)
        self.assertEqual(result["requests"], 1)
        self.assertEqual(
            {d.label for d in repository.finish.call_args.args[2].values()}, {"positive"}
        )
        model_warning_work = group_fragment_works(
            [(consultation, c) for c in consultation.candidates], {10: "Gastrita"}
        )[0].work
        sent = json.loads(client.complete_json.call_args.args[1])
        self.assertEqual(sent["units"]["u0"]["text"], consultation.passage.text)
        self.assertNotIn("segments", sent["units"]["u0"])
        self.assertEqual(model_warning_work[0].start, 0)
        self.assertEqual(model_warning_work[0].end, len(consultation.passage.text))
        raw_key = cache_key(
            model_warning_work,
            {
                **semantic_config(config),
                "herb_name": "menta",
                "condition_name": "Gastrita",
                "condition_synonyms": (),
                "scope_catalog": content_hash([{10: "Gastrita"}, {}]),
            },
            "a" * 64,
        )
        repository.cached.return_value = {
            raw_key: Decision("positive", "model", "", ((0, len(consultation.text)),))
        }
        with (
            patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
            patch("scripts.positive_herb_ranking.make_client") as make_classifier,
            redirect_stdout(output),
        ):
            result = run_positive_ranking(config, repository=repository)
        make_classifier.assert_not_called()
        self.assertEqual(result["requests"], 0)
        self.assertEqual(result["cache_hits"], 2)
        self.assertEqual(
            {d.label for d in repository.finish.call_args.args[2].values()}, {"positive"}
        )
        tomato_names = (*names, ("rosie", (3,)))
        for statement in (
            "Interzis consumul de rosii.",
            "Nu este permis a se consuma rosii.",
            "Nu este permisa consumarea de rosii.",
            "Contraindicat: rosie.",
            "Contraindicate: rosii.",
            "Contraindicate .... rosie",
            "Sunt contraindicate rosiile.",
            "Rosia este contraindicata.",
            "Este contraindicat consumul de roșii.",
            "Contraindicate: rosii, menta si musetel.",
            "## Contraindicate\n- rosii",
            "Interzis:\n- rosii",
        ):
            banned_units = extract_units(
                replace(passage, text=f"# Gastrita\n{statement}\n"), tomato_names, conditions
            )
            self.assertTrue(banned_units, statement)
            banned_works = [(u, c) for u in banned_units for c in u.candidates]
            self.assertIn(3, {c.herb_id for _, c in banned_works}, statement)
            for unit, candidate in banned_works:
                decision = classify_rule(unit, candidate)
                self.assertIsNotNone(decision, statement)
                self.assertEqual(decision.label, "caution", statement)
                self.assertTrue(unit.text[slice(*decision.quotes[0])].strip(), statement)
            repository.read_snapshot.return_value = Snapshot(
                {},
                None,
                (1, 2, 3),
                {1: "menta", 2: "musetel", 3: "rosie"},
                {10: "Gastrita"},
                tuple(banned_works),
            )
            repository.cached.return_value = {}
            with (
                patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
                patch("scripts.positive_herb_ranking.make_client") as make_classifier,
                redirect_stdout(output),
            ):
                result = run_positive_ranking(config, repository=repository)
            make_classifier.assert_not_called()
            self.assertEqual(result["requests"], 0, statement)
            self.assertEqual(
                {d.label for d in repository.finish.call_args.args[2].values()}, {"caution"}
            )
        for statement in (
            "Nu este interzis consumul de rosii.",
            "Nu sunt contraindicate rosiile.",
            "Este interzis consumul de rosii in sarcina.",
            "Contraindicate pentru diabet: rosii.",
            "Interzise doar daca aveti diabet: rosii.",
            "Nu este permis a se consuma mai mult de 2 rosii zilnic.",
            "| interzise | rosii |",
        ):
            uncertain = extract_units(
                replace(passage, text=f"# Gastrita\n{statement}\n"), tomato_names, conditions
            )[0]
            candidate = next(c for c in uncertain.candidates if c.herb_id == 3)
            self.assertIsNone(classify_rule(uncertain, candidate), statement)
            self.assertIsNone(scoped_warning(uncertain, candidate), statement)
        for statement in (
            "Contraindicata carnea rosie.",
            "Nu este permis a se consuma ardei rosii.",
            "Contraindicata varza rosie.",
        ):
            colored = extract_units(
                replace(passage, text=f"# Gastrita\n{statement}\n"), tomato_names, conditions
            )[0]
            self.assertEqual(classify_rule(colored, colored.candidates[0]).label, "unclear")
            self.assertIsNone(scoped_warning(colored, colored.candidates[0]))
        contested = extract_units(
            replace(
                passage,
                text="# Gastrita\nRosii sunt recomandate. Contraindicat consumul de rosii.\n",
            ),
            tomato_names,
            conditions,
        )[0]
        grouped_ban = group_works([(contested, c) for c in contested.candidates])[0][0]
        retained_ban = scoped_warning(*grouped_ban)
        self.assertEqual(retained_ban.label, "caution")
        self.assertEqual(
            combine_decisions([Decision("positive", "model", "", ((0, 23),)), retained_ban]).label,
            "mixed",
        )
        repository.read_snapshot.return_value = Snapshot(
            {},
            None,
            (3,),
            {3: "rosie"},
            {10: "Gastrita"},
            tuple((contested, c) for c in contested.candidates),
        )
        repository.cached.return_value = {}
        client.complete_json.return_value = valid
        with (
            patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
            patch("scripts.positive_herb_ranking.make_client", return_value=client),
            redirect_stdout(output),
        ):
            result = run_positive_ranking(config, repository=repository)
        self.assertEqual(result["requests"], 1)
        self.assertEqual(len(repository.finish.call_args.args[2]), 2)
        self.assertEqual(
            {d.label for d in repository.finish.call_args.args[2].values()}, {"positive"}
        )
        from backend.ai.herb_association_rules import NameMatcher

        self.assertEqual(list(NameMatcher((("rosie", (3,)),)).spans("rosii")), [])
        self.assertEqual(
            list(NameMatcher((("rosie", (3, 4)),), product_forms=True).spans("rosii")), []
        )
        self.assertEqual(
            list(
                NameMatcher((("rosie", (3,)), ("rosii", (4,))), product_forms=True).spans("rosii")
            ),
            [((0, 5), (4,))],
        )
        from contextlib import redirect_stderr
        from unittest.mock import call

        from scripts import positive_herb_ranking as ranking

        oil_names = (
            ("ulei esential de peppermint", (41,)),
            ("ulei esential de lemon", (42,)),
        )
        oil_text = (
            "# Gastrita\nUleiuri recomandate:\n"
            "- ulei esential de Peppermint\n- ulei esential de Lemon\n"
        )
        oil_units = extract_units(
            replace(passage, text=oil_text),
            oil_names,
            conditions,
            herb_categories={41: "uleiuri esentiale", 42: "uleiuri esentiale"},
        )
        self.assertEqual(len(oil_units), 2)
        self.assertEqual(
            [classify_rule(unit, c).label for unit in oil_units for c in unit.candidates],
            ["positive", "positive"],
        )
        mention_units = extract_units(
            replace(passage, text=oil_text.replace("Uleiuri recomandate", "Uleiuri mentionate")),
            oil_names,
            conditions,
        )
        self.assertTrue(
            all(
                decision is None or decision.label != "positive"
                for unit in mention_units
                for c in unit.candidates
                for decision in (classify_rule(unit, c),)
            )
        )
        ambiguous_oil_units = extract_units(
            replace(passage, text=oil_text),
            (("ulei esential de peppermint", (41, 43)),),
            conditions,
        )
        self.assertTrue(
            all(
                classify_rule(unit, c).label == "unclear"
                for unit in ambiguous_oil_units
                for c in unit.candidates
            )
        )

        summary_output = io.StringIO()
        with (
            patch.object(ranking, "run_positive_ranking") as stages,
            redirect_stdout(summary_output),
        ):
            stages.side_effect = [
                {"status": "analyzed"},
                {"status": "ready", "run_id": "prepared-run", "requests": 3, "completed": 3},
                {"status": "published", "run_id": "prepared-run"},
            ]
            published = ranking.refresh_positive_ranking(config)
            self.assertEqual(published["status"], "published")
            self.assertEqual(published["ai_requests_sent_total"], 3)
            self.assertEqual(published["requests"], 3)
            summary = json.loads(summary_output.getvalue().splitlines()[-1])
            self.assertEqual(summary["stage"], "positive_ranking_summary")
            self.assertEqual(summary["ai_requests_sent_total"], 3)
            self.assertEqual(
                stages.call_args_list,
                [call(config, analyze=True), call(config), call(config, publish="prepared-run")],
            )
            stages.reset_mock()
            stages.side_effect = [{"status": "analyzed"}, TimeoutError("synthetic timeout")]
            with self.assertRaises(TimeoutError):
                ranking.refresh_positive_ranking(config)
            self.assertEqual(stages.call_args_list, [call(config, analyze=True), call(config)])

        with (
            patch("backend.config.Settings.from_env", return_value=config) as environment_settings,
            patch("backend.config.configure_settings") as configure,
            patch.object(builder, "build") as build_index,
            patch.object(builder, "rebuild_herbs_only") as rebuild_associations,
            patch.object(ranking, "refresh_positive_ranking") as refresh_rankings,
            patch.object(ranking, "run_positive_ranking") as explicit_stage,
            redirect_stdout(output),
            redirect_stderr(output),
        ):
            ordering = Mock()
            ordering.attach_mock(build_index, "index")
            ordering.attach_mock(refresh_rankings, "rankings")
            with patch("sys.argv", ["build_hybrid_index"]):
                self.assertEqual(builder.main(), 0)
            self.assertEqual([c[0] for c in ordering.mock_calls], ["index", "rankings", "rankings"])
            refresh_rankings.reset_mock()
            with patch("sys.argv", ["build_hybrid_index", "--skip-positive-ranking"]):
                self.assertEqual(builder.main(), 0)
            refresh_rankings.assert_not_called()
            with patch("sys.argv", ["build_hybrid_index", "--rebuild-herbs-only"]):
                self.assertEqual(builder.main(), 0)
            rebuild_associations.assert_called_once()
            self.assertEqual(refresh_rankings.call_count, 2)
            refresh_rankings.reset_mock()
            with patch("sys.argv", ["build_hybrid_index", "--prepare-positive-ranking"]):
                self.assertEqual(builder.main(), 0)
            explicit_stage.assert_called_once_with(
                builder.settings, analyze=False, publish=None, resume=None
            )
            with patch("scripts.herb_safety_index.run_safety_index") as safety_stage:
                with patch("sys.argv", ["build_hybrid_index", "--analyze-safety-warnings"]):
                    self.assertEqual(builder.main(), 0)
                safety_stage.assert_called_once_with(
                    builder.settings, analyze=True, publish=None, resume=None
                )
            refresh_rankings.assert_not_called()
            build_index.side_effect = RuntimeError("synthetic index failure")
            with patch("sys.argv", ["build_hybrid_index"]):
                self.assertEqual(builder.main(), 1)
            refresh_rankings.assert_not_called()
            build_index.side_effect = None
            refresh_rankings.side_effect = RuntimeError("synthetic corpus text")
            with patch("sys.argv", ["build_hybrid_index"]):
                self.assertEqual(builder.main(), 1)
            self.assertNotIn("synthetic corpus text", output.getvalue())
            self.assertIn("POSITIVE_RANKING_FAILED", output.getvalue())
            with patch(
                "sys.argv",
                ["build_hybrid_index", "--skip-positive-ranking", "--prepare-positive-ranking"],
            ):
                with self.assertRaises(SystemExit):
                    builder.parse_args()
            refresh_rankings.side_effect = None
            environment_settings.return_value = replace(
                config, herb_association_ai_base="http://host.docker.internal:11434/v1"
            )
            with (
                patch("sys.argv", ["build_hybrid_index", "--skip-positive-ranking"]),
                patch("sys.platform", "win32"),
            ):
                self.assertEqual(builder.main(), 0)
            self.assertEqual(
                configure.call_args.args[0].herb_association_ai_base,
                "http://127.0.0.1:11434/v1",
            )
            with (
                patch("sys.argv", ["build_hybrid_index", "--skip-positive-ranking"]),
                patch("sys.platform", "linux"),
            ):
                self.assertEqual(builder.main(), 0)
            self.assertEqual(
                configure.call_args.args[0].herb_association_ai_base,
                "http://host.docker.internal:11434/v1",
            )

        from backend.ai.herb_safety_extraction import SafetyTarget
        from backend.ai.herb_safety_repository import SafetyRepository, SafetySnapshot
        from backend.ai.herb_safety_validation import (
            SafetyResult,
            decode_result,
            encode_result,
            validate_warnings,
        )
        from scripts.herb_safety_index import (
            SafetyCoordinator,
            batch_progress,
            format_duration,
            safety_payload,
            workflow_progress,
        )
        from scripts.herb_safety_index import (
            _run_legacy_safety_index as run_safety_index,
        )

        safety_text = "Menta poate provoca somnolenta la doze mari; nu se asociaza cu warfarina."
        safety_target = SafetyTarget(
            7,
            1,
            "menta",
            "synthetic.md",
            "a" * 64,
            "b" * 64,
            "Menta",
            safety_text,
            ((0, 5),),
            heading_owned=True,
        )
        repeated_target = replace(safety_target, chunk_id=8)
        safety_data = SafetySnapshot({}, (safety_target, repeated_target))
        safety_repository = Mock(spec=SafetyRepository)
        safety_repository.read_snapshot.return_value = safety_data
        safety_repository.cached.return_value = {}
        safety_repository.create_run.return_value = "preparing"
        warning_response = {
            "s0": {
                "status": "complete",
                "items": [
                    {
                        "kind": "drug_interaction",
                        "quote": safety_text,
                        "partners": ["warfarina"],
                    }
                ],
            }
        }
        reference_response = {
            "s0": {
                "status": "complete",
                "items": [
                    {
                        "kind": "drug_interaction",
                        "passage_ids": ["c7p0"],
                        "focus_id": "c7p0s1",
                        "summary": safety_text,
                        "partners": ["warfarina"],
                    }
                ],
            }
        }
        warning_client = Mock()
        warning_client.complete_json.return_value = {"warnings": reference_response}
        warning_factory = Mock(return_value=warning_client)
        coordinator = SafetyCoordinator(config, safety_repository, "local-run", "a" * 64)
        safety_summary = coordinator.prepare(
            {safety_target.identity, repeated_target.identity},
            client_factory=warning_factory,
            digest_verifier=lambda _settings: "a" * 64,
        )
        self.assertEqual(safety_summary["warnings_only_ai_requests"], 1)
        self.assertEqual(safety_summary["safety_context_tokens"], 65536)
        self.assertEqual(
            warning_factory.call_args.args[0].herb_association_ai_context_tokens, 65536
        )
        self.assertEqual(config.herb_association_ai_context_tokens, 32768)
        warning_client.complete_json.assert_called_once()
        sent = json.loads(warning_client.complete_json.call_args.args[1])
        self.assertNotIn("candidates", sent)
        self.assertEqual(len(sent["units"]), 1)
        self.assertEqual(sent["units"]["u0"]["text"], safety_text)
        persisted = safety_repository.finish.call_args.args[2]
        self.assertEqual(set(persisted), {safety_target.identity, repeated_target.identity})
        self.assertTrue(all(result.items[0].text == safety_text for result in persisted.values()))
        checked = validate_warnings(warning_response, [safety_target])[safety_target.identity]
        self.assertEqual(decode_result(encode_result(checked), safety_target), checked)

        import httpx

        from backend.core.errors import OperationCancelled
        from backend.core.operation_context import OperationBudget, operation_budget
        from scripts.herb_index_requests import make_client as streaming_client

        response_text = json.dumps({"warnings": reference_response}, ensure_ascii=False)
        split = len(response_text) // 2
        native_events = [
            {"message": {"content": response_text[:split]}, "done": False},
            {"message": {"content": response_text[split:]}, "done": False},
            {
                "message": {"content": ""},
                "done": True,
                "done_reason": "stop",
                "load_duration": 100_000_000,
                "prompt_eval_duration": 900_000_000,
                "eval_duration": 2_000_000_000,
                "total_duration": 3_000_000_000,
                "prompt_eval_count": 100,
                "prompt_eval_cached_count": 60,
                "eval_count": 20,
            },
        ]
        for mode in ("completed", "interrupted", "timeout", "deadline", "parent_deadline"):
            stream_clock = [1000.0]
            native_calls = []

            class NativeStream(httpx.SyncByteStream):
                def __iter__(self):
                    for index, event in enumerate(native_events):
                        if mode == "interrupted" and index == 1:
                            return
                        if mode == "timeout" and index == 1:
                            raise httpx.ReadTimeout("synthetic transport timeout")
                        stream_clock[0] += (
                            config.herb_association_ai_timeout_seconds + 1.0
                            if mode == "deadline"
                            else 1.0
                        )
                        if mode == "parent_deadline":
                            stream_clock[0] += 1.0
                        yield (json.dumps(event, ensure_ascii=False) + "\n").encode()

            def native_handler(request):
                native_calls.append(request)
                return httpx.Response(200, stream=NativeStream())

            native_client = streaming_client(
                replace(
                    config, herb_association_ai_context_tokens=config.herb_safety_ai_context_tokens
                )
            )
            native_client.http.close()
            native_client.http = httpx.Client(
                transport=httpx.MockTransport(native_handler), trust_env=False
            )
            safety_repository.read_snapshot.return_value = safety_data
            safety_repository.cached.return_value = {}
            safety_repository.save_cache.reset_mock()
            safety_repository.finish.reset_mock()
            native_coordinator = SafetyCoordinator(
                config,
                safety_repository,
                "native-stream-run",
                "a" * 64,
                clock=lambda: stream_clock[0],
            )
            native_output = io.StringIO()
            with (
                redirect_stdout(native_output),
                self.assertLogs("naturist.ai", level="INFO") as logs,
            ):
                if mode == "completed":
                    native_coordinator.prepare(
                        {safety_target.identity, repeated_target.identity},
                        client_factory=lambda _settings: native_client,
                        digest_verifier=lambda _settings: "a" * 64,
                    )
                elif mode == "parent_deadline":
                    with (
                        self.assertRaises(OperationCancelled),
                        operation_budget(
                            OperationBudget(1001.0, lambda: stream_clock[0], lambda: None)
                        ),
                    ):
                        native_coordinator.prepare(
                            {safety_target.identity}, client_factory=lambda _settings: native_client
                        )
                else:
                    with self.assertRaises(AIUnavailable) as failed_stream:
                        native_coordinator.prepare(
                            {safety_target.identity}, client_factory=lambda _settings: native_client
                        )
                    self.assertEqual(
                        failed_stream.exception.reason,
                        "invalid_response" if mode == "interrupted" else "timeout",
                    )
            self.assertEqual(len(native_calls), 1)
            wire = json.loads(native_calls[0].content)
            self.assertIs(wire["stream"], True)
            self.assertIs(wire["think"], False)
            self.assertIs(wire["truncate"], False)
            self.assertEqual(wire["options"]["num_ctx"], 65536)
            self.assertEqual(wire["options"]["num_predict"], 25000)
            self.assertEqual(
                json.loads(wire["messages"][1]["content"])["units"]["u0"]["text"], safety_text
            )
            rows = [json.loads(line) for line in native_output.getvalue().splitlines()]
            self.assertEqual(
                [row["event"] for row in rows],
                ["started", "completed" if mode == "completed" else "failed"],
            )
            metrics = rows[-1]
            self.assertEqual(metrics["source_chars"], len(safety_text))
            self.assertEqual(metrics["fragments"], 1)
            self.assertNotIn(safety_text, native_output.getvalue())
            self.assertNotIn(safety_text, "\n".join(logs.output))
            self.assertEqual(native_coordinator.counters["warnings_only_ai_requests"], 1)
            if mode == "completed":
                self.assertEqual(metrics["first_chunk_ms"], 1000.0)
                self.assertEqual(metrics["first_output_ms"], 1000.0)
                self.assertEqual(metrics["duration_ms"], 3000.0)
                self.assertEqual(metrics["stream_events"], 3)
                self.assertEqual(metrics["output_chars"], len(response_text))
                self.assertEqual(metrics["thinking_chars"], 0)
                self.assertEqual(metrics["prompt_eval_count"], 100)
                self.assertEqual(metrics["prompt_eval_cached_count"], 60)
                self.assertEqual(metrics["load_duration_ms"], 100.0)
                self.assertEqual(metrics["prompt_eval_duration_ms"], 900.0)
                self.assertEqual(metrics["eval_duration_ms"], 2000.0)
                self.assertEqual(metrics["output_tokens_per_second"], 10.0)
                self.assertEqual(native_coordinator.counters["safety_batches_completed"], 1)
                safety_repository.save_cache.assert_called_once()
                safety_repository.finish.assert_called_once()
            else:
                self.assertIsNone(metrics["eval_duration_ms"])
                self.assertEqual(native_coordinator.counters["safety_batches_completed"], 0)
                safety_repository.save_cache.assert_not_called()
                safety_repository.finish.assert_not_called()

        with self.assertRaisesRegex(ValueError, "HERB_SAFETY_UNSUPPORTED_QUOTE"):
            validate_warnings(
                {
                    "s0": {
                        "status": "complete",
                        "items": [
                            {
                                "kind": "drug_interaction",
                                "quote": "Afirmatie inexistenta",
                                "partners": [],
                            }
                        ],
                    }
                },
                [safety_target],
            )
        with self.assertRaisesRegex(ValueError, "HERB_SAFETY_INCOMPLETE_RESPONSE"):
            validate_warnings({}, [safety_target])
        self.assertEqual(response_schema(safety_payload([safety_target]))["required"], ["warnings"])
        ambiguous_target = replace(
            safety_target, herb_id=2, certain=False, mentions=(), heading_owned=False
        )
        mixed_targets = [safety_target, ambiguous_target]
        mixed_schema = response_schema(safety_payload(mixed_targets))
        entries = mixed_schema["properties"]["warnings"]["properties"]
        self.assertEqual(entries["s0"]["properties"]["status"]["enum"], ["complete", "unclear"])
        self.assertEqual(entries["s1"]["properties"]["status"]["enum"], ["unclear"])
        self.assertNotIn("maxItems", entries["s0"]["properties"]["items"])
        self.assertEqual(entries["s1"]["properties"]["items"]["maxItems"], 0)
        mixed_response = {**warning_response, "s1": {"status": "unclear", "items": []}}
        mixed_results = validate_warnings(mixed_response, mixed_targets)
        self.assertEqual(mixed_results[ambiguous_target.identity], SafetyResult("unclear"))
        self.assertEqual(
            decode_result(
                encode_result(mixed_results[ambiguous_target.identity]), ambiguous_target
            ),
            SafetyResult("unclear"),
        )
        for ambiguous_response in (
            {"status": "complete", "items": []},
            {"status": "unclear", "items": warning_response["s0"]["items"]},
        ):
            with self.assertRaisesRegex(ValueError, "HERB_SAFETY_AMBIGUOUS_TARGET"):
                validate_warnings({"s0": ambiguous_response}, [ambiguous_target])
        safety_repository.read_snapshot.return_value = SafetySnapshot({}, tuple(mixed_targets))
        safety_repository.cached.return_value = {}
        warning_client.complete_json.return_value = {
            "warnings": {**reference_response, "s1": {"status": "unclear", "items": []}}
        }
        mixed = SafetyCoordinator(config, safety_repository, "mixed-run", "a" * 64)
        mixed.prepare(
            {target.identity for target in mixed_targets},
            client_factory=warning_factory,
            digest_verifier=lambda _settings: "a" * 64,
        )
        self.assertEqual(safety_repository.finish.call_args.args[2], mixed_results)
        self.assertEqual(mixed.counters["warnings_only_ai_requests"], 1)

        self.assertIsNone(batch_progress(0, 265, 0)["ETA(hh:mm:ss)"])
        self.assertIsNone(batch_progress(0, None, 120)["ETA(hh:mm:ss)"])
        self.assertEqual(batch_progress(0, 0, 0)["ETA(hh:mm:ss)"], "00:00:00")
        self.assertEqual(batch_progress(1, 265, 10)["ETA(hh:mm:ss)"], "00:44:00")
        self.assertEqual(batch_progress(1, 2, 0.1)["ETA(hh:mm:ss)"], "00:00:01")
        self.assertEqual(format_duration(90061), "25:01:01")
        for stage in (
            "analysis",
            "associations",
            "safety_inventory",
            "ranking_preparation",
            "caution_preparation",
            "safety_preparation",
            "safety_finalization",
        ):
            preparing = workflow_progress(
                {"progress_stage": stage, "completed": 0, "batches": 0}, 60
            )
            self.assertEqual(preparing["progress_stage"], stage)
            self.assertIsNone(preparing["ETA(hh:mm:ss)"])
        self.assertIsNone(
            workflow_progress(
                {"progress_stage": "analysis", "status": "analyzed", "completed": 0, "batches": 0},
                17,
            )["ETA(hh:mm:ss)"]
        )
        clock_value = [5000.0]
        measured_progress = []
        safety_repository.cached.return_value = {}
        timed = SafetyCoordinator(
            replace(config, herb_association_ai_max_pairs=1),
            safety_repository,
            "timed-run",
            "a" * 64,
            clock=lambda: clock_value[0],
        )
        self.assertIsNone(timed.progress_metrics())
        timed_client = Mock()

        def timed_response(_system, user, _tokens):
            measured_progress.append({**timed.counters, **timed.progress_metrics()})
            clock_value[0] += 10.0
            return {
                "warnings": {
                    target["id"]: {
                        "status": "complete" if target["certain"] else "unclear",
                        "items": [],
                    }
                    for target in json.loads(user)["safety_targets"]
                }
            }

        timed_client.complete_json.side_effect = timed_response
        timed.prepare(
            {target.identity for target in mixed_targets},
            client_factory=lambda _settings: timed_client,
            digest_verifier=lambda _settings: "a" * 64,
        )
        self.assertEqual(measured_progress[0]["warnings_only_ai_requests"], 1)
        self.assertEqual(measured_progress[0]["safety_batches_completed"], 0)
        self.assertIsNone(measured_progress[0]["ETA(hh:mm:ss)"])
        self.assertEqual(measured_progress[1]["warnings_only_ai_requests"], 2)
        self.assertEqual(measured_progress[1]["safety_batches_completed"], 1)
        self.assertEqual(measured_progress[1]["progress_stage"], "warnings_only")
        self.assertEqual(measured_progress[1]["rate_batches_second"], 0.1)
        self.assertEqual(measured_progress[1]["ETA(hh:mm:ss)"], "00:00:10")
        active_warning_progress = workflow_progress(
            {**measured_progress[1], "completed": 0, "batches": 0},
            5010,
            measured_progress[1],
        )
        self.assertEqual(active_warning_progress["progress_stage"], "warnings_only")
        self.assertEqual(active_warning_progress["ETA(hh:mm:ss)"], "00:00:10")
        self.assertEqual(timed.counters["safety_batches_completed"], 2)
        clock_value[0] += 300.0
        self.assertEqual(timed.progress_metrics()["rate_batches_second"], 0.1)
        self.assertEqual(timed.progress_metrics()["ETA(hh:mm:ss)"], "00:00:00")

        safety_repository.cached.return_value = dict(mixed_results)
        standalone_output = io.StringIO()
        with (
            patch("scripts.herb_safety_index.SafetyRepository", return_value=safety_repository),
            patch("scripts.herb_safety_index.PositiveRepository"),
            patch(
                "scripts.herb_safety_index.local_target_ids",
                return_value={target.identity for target in mixed_targets},
            ),
            patch("scripts.herb_safety_index.model_digest", return_value="a" * 64),
            redirect_stdout(standalone_output),
        ):
            standalone = run_safety_index(config)
            standalone_progress = json.loads(standalone_output.getvalue().splitlines()[-1])
            run_safety_index(config, publish=standalone["run_id"])
            publication_progress = json.loads(standalone_output.getvalue().splitlines()[-1])
        self.assertEqual(standalone["warnings_only_ai_requests"], 0)
        self.assertEqual(standalone_progress["safety_batches_completed"], 0)
        self.assertEqual(standalone_progress["progress_stage"], "ready")
        self.assertEqual(standalone_progress["ETA(hh:mm:ss)"], "00:00:00")
        self.assertEqual(publication_progress["status"], "published")
        self.assertEqual(publication_progress["ETA(hh:mm:ss)"], "00:00:00")

        from backend.ai.herb_caution_repository import CautionRepository
        from backend.ai.herb_product_safety_repository import ProductSafetyRepository

        empty_repository = Mock(spec=PositiveRepository)
        empty_repository.read_snapshot.return_value = Snapshot(
            {}, None, (1,), {1: "menta"}, {10: "Gastrita"}, ()
        )
        empty_repository.cached.return_value = {}
        empty_repository.create_run.return_value = {"status": "preparing"}
        projection = Mock(spec=CautionRepository)
        product_repository = Mock(spec=ProductSafetyRepository)
        product_repository.read_products.return_value = ()
        product_repository.cached.return_value = {}
        product_repository.create_run.return_value = "preparing"
        projection_progress = []

        def capture_projection(_run_id, _settings):
            current = empty_repository.finish.call_args.args[-1]
            projection_progress.append(workflow_progress(current, 60))
            return {"run_id": "projection-run", "unknown_count": 0}

        projection.prepare.side_effect = capture_projection
        full_output = io.StringIO()
        with (
            patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
            patch(
                "scripts.positive_herb_ranking.make_client",
                side_effect=AssertionError("No AI expected with the complete cache"),
            ),
            redirect_stdout(full_output),
        ):
            run_positive_ranking(
                config,
                repository=empty_repository,
                caution_repository=projection,
                safety_repository=product_repository,
            )
        self.assertEqual(projection_progress[0]["progress_stage"], "caution_preparation")
        self.assertIsNone(projection_progress[0]["ETA(hh:mm:ss)"])
        finished_progress = json.loads(full_output.getvalue().splitlines()[-1])
        self.assertEqual(finished_progress["status"], "ready")
        self.assertEqual(finished_progress["ETA(hh:mm:ss)"], "00:00:00")

        foreign_quote = "Busuiocul nu se administreaza copiilor."
        scoped_target = replace(
            safety_target, text=f"{safety_text}\n\n{foreign_quote}", heading_owned=False
        )
        scoped_repeat = replace(scoped_target, chunk_id=8)
        ambiguous_target = replace(ambiguous_target, chunk_id=9)
        partial_data = SafetySnapshot({}, (scoped_target, scoped_repeat, ambiguous_target))
        partial_response = {
            "s0": {
                "status": "complete",
                "items": [
                    *reference_response["s0"]["items"],
                    {
                        "kind": "adverse_effect",
                        "passage_ids": ["unknown"],
                        "focus_id": "c7p0s1",
                        "summary": "Afirmatie nesustinuta.",
                        "partners": [],
                    },
                    {
                        "kind": "population",
                        "passage_ids": ["c7p1"],
                        "focus_id": "c7p1s0",
                        "summary": foreign_quote,
                        "partners": [],
                    },
                    {
                        "kind": "drug_interaction",
                        "passage_ids": ["c7p0"],
                        "focus_id": "c7p0s1",
                        "summary": safety_text,
                        "partners": ["aspirina"],
                    },
                ],
            },
            "s1": {"status": "unclear", "items": []},
        }
        safety_repository.read_snapshot.return_value = partial_data
        safety_repository.cached.return_value = {}
        warning_client.complete_json.return_value = {"warnings": partial_response}
        partial = SafetyCoordinator(config, safety_repository, "partial-run", "a" * 64)
        partial.prepare(
            {target.identity for target in partial_data.targets},
            client_factory=warning_factory,
            digest_verifier=lambda _settings: "a" * 64,
        )
        partial_results = safety_repository.finish.call_args.args[2]
        self.assertEqual(
            partial_results[scoped_target.identity], SafetyResult("unclear", checked.items)
        )
        self.assertEqual(
            partial_results[scoped_repeat.identity], partial_results[scoped_target.identity]
        )
        self.assertEqual(partial_results[ambiguous_target.identity], SafetyResult("unclear"))
        self.assertEqual(partial.counters["safety_rejected_quotes"], 3)
        self.assertEqual(partial.counters["safety_rejected_passage_id"], 1)
        self.assertEqual(partial.counters["safety_rejected_quote_scope"], 1)
        self.assertEqual(partial.counters["safety_rejected_partner"], 1)
        self.assertEqual(partial.counters["safety_unclear_after_validation"], 1)
        self.assertEqual(partial.counters["warnings_only_ai_requests"], 1)
        self.assertEqual(
            decode_result(encode_result(partial_results[scoped_target.identity]), scoped_target),
            partial_results[scoped_target.identity],
        )
        safety_repository.save_cache.reset_mock()
        with self.assertRaisesRegex(ValueError, "HERB_SAFETY_INVALID_RESPONSE"):
            partial.record(
                {**partial_response, "s1": {"status": "invalid", "items": []}},
                [scoped_target, ambiguous_target],
            )
        safety_repository.save_cache.assert_not_called()
        safety_repository.cached.return_value = {
            scoped_target.identity: partial_results[scoped_target.identity],
            ambiguous_target.identity: partial_results[ambiguous_target.identity],
        }
        no_partial_calls = Mock()
        resumed_partial = SafetyCoordinator(
            config, safety_repository, "partial-run", "a" * 64, resume=True
        )
        resumed_partial.prepare(
            {target.identity for target in partial_data.targets}, client_factory=no_partial_calls
        )
        no_partial_calls.assert_not_called()
        self.assertEqual(resumed_partial.counters["safety_cache_hits"], 3)
        self.assertEqual(safety_repository.finish.call_args.args[2], partial_results)
        safety_repository.cached.return_value = {}
        partial_combined = SafetyCoordinator(
            config, safety_repository, "partial-combined", "a" * 64
        )
        partial_combined.record(partial_response, [scoped_target, ambiguous_target], combined=True)
        partial_combined.prepare(
            {target.identity for target in partial_data.targets}, client_factory=no_partial_calls
        )
        no_partial_calls.assert_not_called()
        self.assertEqual(partial_combined.counters.get("safety_invalid_combined", 0), 0)
        self.assertEqual(safety_repository.finish.call_args.args[2], partial_results)

        safety_repository.read_snapshot.return_value = safety_data
        safety_repository.cached.return_value = {
            safety_target.identity: SafetyResult("complete"),
            repeated_target.identity: SafetyResult("complete"),
        }
        no_calls = Mock()
        SafetyCoordinator(config, safety_repository, "cached-run", "a" * 64).prepare(
            {safety_target.identity, repeated_target.identity}, client_factory=no_calls
        )
        no_calls.assert_not_called()
        safety_repository.cached.return_value = {}
        combined = SafetyCoordinator(config, safety_repository, "combined-run", "a" * 64)
        mint_work = (
            replace(
                work[0],
                passage=replace(work[0].passage, chunk_id=7, text=safety_text),
                start=0,
                end=len(safety_text),
            ),
            work[1],
        )
        combined_payload, warning_targets = combined.enrich(
            serialize_batch([mint_work], {1: "menta"}, {10: "Gastrita"}), [mint_work]
        )
        self.assertTrue(warning_targets)
        self.assertIn("warnings", response_schema(json.loads(combined_payload))["required"])
        combined.record(reference_response, warning_targets, combined=True)
        combined.prepare({safety_target.identity}, client_factory=no_calls)
        no_calls.assert_not_called()
        self.assertEqual(combined.counters["warnings_only_ai_requests"], 0)


class EmbeddingProgressTests(unittest.TestCase):
    def test_reports_periodic_progress_and_completion(self):
        chunks = [make_chunk(index) for index in range(1, 4)]
        output = io.StringIO()

        with redirect_stdout(output):
            embeddings = builder.embed_chunks(
                FakeEmbeddingModel(3),
                chunks,
                batch_size=64,
                profile=QWEN,
                clock=FakeClock(0.0, 3.0, 11.0, 12.0, 15.0),
            )

        log = output.getvalue()
        self.assertIn("Embedding progress: 2/3 (66.7%)", log)
        self.assertIn("elapsed 00:00:11", log)
        self.assertIn("ETA 00:00:05", log)
        self.assertIn("Embedding completed: 3/3 (100.0%)", log)
        self.assertEqual(embeddings.shape, (3, QWEN.dimension))
        np.testing.assert_allclose(np.linalg.norm(embeddings, axis=1), np.ones(3))

    def test_short_run_still_reports_completion(self):
        output = io.StringIO()

        with redirect_stdout(output):
            builder.embed_chunks(
                FakeEmbeddingModel(1),
                [make_chunk(1)],
                batch_size=64,
                profile=QWEN,
                clock=FakeClock(0.0, 1.0, 2.0),
            )

        log = output.getvalue()
        self.assertNotIn("Embedding progress:", log)
        self.assertIn("Embedding completed: 1/1 (100.0%)", log)

    def test_oversized_chunk_is_embedded_on_windows_and_averaged(self):
        # Deterministic per-input-index unit vectors, so we can tell how many
        # documents a call actually embedded without depending on a real model.
        class WindowModel:
            def embed(self, documents, batch_size, parallel):
                for index, _ in enumerate(documents):
                    vector = np.zeros(QWEN.dimension, dtype=np.float32)
                    vector[index % QWEN.dimension] = 1.0
                    yield vector

        long_chunk = make_chunk(1, text="Propoziție. " * 300)
        self.assertGreater(len(long_chunk.text), QWEN.max_chars)
        windows = len(builder._embedding_windows(long_chunk, QWEN))
        self.assertGreater(windows, 1)
        output = io.StringIO()

        with redirect_stdout(output):
            embeddings = builder.embed_chunks(
                WindowModel(),
                [long_chunk],
                batch_size=64,
                profile=QWEN,
                clock=FakeClock(0.0, *([1.0] * windows), 5.0),
            )

        self.assertEqual(embeddings.shape, (1, QWEN.dimension))
        np.testing.assert_allclose(np.linalg.norm(embeddings, axis=1), [1.0], atol=1e-6)
        self.assertIn("Embedding completed: 1/1 (100.0%)", output.getvalue())

    def test_short_and_oversized_chunks_land_at_their_original_positions(self):
        class WindowModel:
            def embed(self, documents, batch_size, parallel):
                for index, _ in enumerate(documents):
                    vector = np.zeros(QWEN.dimension, dtype=np.float32)
                    vector[index % QWEN.dimension] = 1.0
                    yield vector

        chunks = [
            make_chunk(1, text="scurt"),
            make_chunk(2, text="Propoziție. " * 300),
            make_chunk(3, text="scurt2"),
        ]
        windows = sum(len(builder._embedding_windows(chunk, QWEN)) for chunk in chunks)

        embeddings = builder.embed_chunks(
            WindowModel(),
            chunks,
            batch_size=64,
            profile=QWEN,
            clock=FakeClock(0.0, *([1.0] * windows), 3.0),
        )

        self.assertEqual(embeddings.shape, (3, QWEN.dimension))
        for row in embeddings:
            self.assertAlmostEqual(float(np.linalg.norm(row)), 1.0, places=5)

    def test_a_long_chunk_averages_only_its_own_windows(self):
        # Window i of the whole batch gets the unit vector e_i, so a chunk's
        # embedding must be the normalized mean of exactly its own windows.
        class WindowModel:
            def embed(self, documents, batch_size, parallel):
                for index, _ in enumerate(documents):
                    vector = np.zeros(QWEN.dimension, dtype=np.float32)
                    vector[index] = 1.0
                    yield vector

        chunks = [make_chunk(1, text="scurt"), make_chunk(2, text="Propoziție. " * 300)]
        long_windows = len(builder._embedding_windows(chunks[1], QWEN))

        embeddings = builder.embed_chunks(WindowModel(), chunks, batch_size=64, profile=QWEN)

        np.testing.assert_allclose(embeddings[0][0], 1.0)
        expected = np.zeros(QWEN.dimension, dtype=np.float32)
        expected[1 : 1 + long_windows] = 1.0 / np.sqrt(long_windows)
        np.testing.assert_allclose(embeddings[1], expected, atol=1e-6)

    def test_embedding_failure_is_propagated_without_false_completion(self):
        output = io.StringIO()

        with self.assertRaisesRegex(RuntimeError, "embedding failed"), redirect_stdout(output):
            builder.embed_chunks(
                FakeEmbeddingModel(3, fail_after=1),
                [make_chunk(index) for index in range(1, 4)],
                batch_size=64,
                profile=QWEN,
                clock=FakeClock(0.0, 11.0),
            )

        self.assertNotIn("Embedding completed", output.getvalue())


class EmbeddingProfileTests(unittest.TestCase):
    def test_qwen_puts_an_instruction_before_the_query_and_no_prefix_before_passages(self):
        query = QWEN.query_text("ceai pentru tuse")

        self.assertTrue(query.startswith("Instruct: "))
        self.assertTrue(query.endswith("\nQuery:ceai pentru tuse"))
        self.assertEqual(QWEN.passage_text("Titlu\ntext"), "Titlu\ntext")
        self.assertEqual(QWEN.dimension, 1024)

    def test_braces_in_a_question_are_not_template_syntax(self):
        self.assertEqual(QWEN.query_text("{text} {0}").split("Query:")[1], "{text} {0}")

    def test_windows_follow_the_profile(self):
        chunk = make_chunk(1, text="Propoziție. " * 300)

        qwen_windows = builder._embedding_windows(chunk, QWEN)
        prefixed = builder._embedding_windows(
            chunk, dataclasses.replace(QWEN, passage_template="passage: {text}")
        )

        self.assertGreater(len(qwen_windows), 1)
        self.assertTrue(qwen_windows[0].startswith("document\nTitlu\n"))
        self.assertEqual(prefixed, ["passage: " + window for window in qwen_windows])

    def test_unknown_model_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown embedding model"):
            get_profile("nu/exista")


def make_source(relative_path: str, category_id: str) -> builder.SourceFile:
    return builder.SourceFile(
        relative_path=relative_path,
        absolute_path=f"C:/documents/{relative_path}",
        size_bytes=10,
        modified_utc="2026-01-01T00:00:00Z",
        sha256="hash",
        encoding="utf-8",
        line_count=1,
        char_count=10,
        category_id=category_id,
    )


class CategoryTreeTests(unittest.TestCase):
    def test_builds_recursive_tree_from_folder_structure(self):
        sources = [
            make_source("Cancer/a.md", "Cancer"),
            make_source("Cancer/b.md", "Cancer"),
            make_source("Centrul de studii/Anatomie/c.md", "Centrul de studii/Anatomie"),
            make_source("root.md", ""),
        ]

        tree = categories.build_category_tree(sources)

        self.assertEqual(tree["root_id"], "")
        nodes = tree["nodes"]
        self.assertEqual(
            set(nodes), {"", "Cancer", "Centrul de studii", "Centrul de studii/Anatomie"}
        )

        # "Cancer" has documents of its own and no children.
        self.assertEqual(nodes["Cancer"]["own_documents"], 2)
        self.assertEqual(nodes["Cancer"]["total_documents"], 2)
        self.assertEqual(nodes["Cancer"]["children"], [])
        self.assertEqual(nodes["Cancer"]["parent"], "")

        # "Centrul de studii" is a purely structural ancestor: no document of
        # its own, but its subfolder's document counts toward its total.
        self.assertEqual(nodes["Centrul de studii"]["own_documents"], 0)
        self.assertEqual(nodes["Centrul de studii"]["total_documents"], 1)
        self.assertEqual(nodes["Centrul de studii"]["children"], ["Centrul de studii/Anatomie"])

        self.assertEqual(nodes["Centrul de studii/Anatomie"]["own_documents"], 1)
        self.assertEqual(nodes["Centrul de studii/Anatomie"]["label"], "Anatomie")
        self.assertEqual(nodes["Centrul de studii/Anatomie"]["parent"], "Centrul de studii")

        # The root category (files with no folder) and the whole-tree total.
        self.assertEqual(nodes[""]["own_documents"], 1)
        self.assertEqual(nodes[""]["total_documents"], 4)
        self.assertEqual(set(nodes[""]["children"]), {"Cancer", "Centrul de studii"})

    def test_root_children_are_sorted_case_insensitively(self):
        sources = [
            make_source("zebra/a.md", "zebra"),
            make_source("Alpha/b.md", "Alpha"),
            make_source("beta/c.md", "beta"),
        ]

        tree = categories.build_category_tree(sources)

        self.assertEqual(tree["nodes"][""]["children"], ["Alpha", "beta", "zebra"])

    def test_deeply_nested_folders_each_become_their_own_category(self):
        sources = [make_source("A/B/C/D/doc.md", "A/B/C/D")]

        tree = categories.build_category_tree(sources)

        self.assertEqual(set(tree["nodes"]), {"", "A", "A/B", "A/B/C", "A/B/C/D"})
        self.assertEqual(tree["nodes"]["A/B/C/D"]["total_documents"], 1)
        self.assertEqual(tree["nodes"]["A"]["total_documents"], 1)
        for ancestor in ("A", "A/B", "A/B/C"):
            self.assertEqual(tree["nodes"][ancestor]["own_documents"], 0)


if __name__ == "__main__":
    unittest.main()
