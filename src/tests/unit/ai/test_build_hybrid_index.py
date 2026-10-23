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
        self.assertEqual(classify_rule(ingredient, ingredient.candidates[0]).label, "unclear")
        book_scope = extract_units(
            replace(
                passage,
                heading="Tratamente si recomandari generale > Gastrita. Tratament",
                text="- gemoderivat de menta: 1 doza sau 2ml pe zi timp de maxim o luna.\n",
            ),
            names,
            conditions,
        )[0]
        self.assertEqual(classify_rule(book_scope, book_scope.candidates[0]).label, "unclear")
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
            self.assertEqual(classify_rule(named, named.candidates[0]).label, "unclear")
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

        work = (fallback, fallback.candidates[0])
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
        valid = {"relations": {"r0": [1, "a"]}}
        self.assertEqual(validate_response(valid, [work])[identifier].label, "positive")
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
        unclear = {"relations": {"r0": [0]}}
        repeated_mixed = {"relations": {"r0": [3, "a", "a"]}}
        self.assertEqual(
            validate_response(repeated_mixed, [work])[identifier],
            Decision("mixed", "model", "", ((0, len(fallback.text)),)),
        )
        self.assertEqual(
            validate_response(unclear, [work])[identifier], Decision("unclear", "model", "")
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
        payload = json.loads(serialize_batch(isolated, {1: "menta"}, {10: "Gastrita"}))
        schema = response_schema(payload)
        self.assertIn("b", schema["$defs"]["u1"]["enum"])
        self.assertNotIn("a", schema["$defs"]["u1"]["enum"])
        self.assertEqual(
            schema["properties"]["relations"]["properties"]["r1"],
            {"$ref": "#/$defs/u1_decision"},
        )
        self.assertEqual(payload["units"]["u1"]["segments"][0]["start"], 0)
        for candidate in payload["candidates"]:
            original = "".join(
                p["text"]
                for s in payload["units"][candidate["unit"]]["segments"]
                for p in s["parts"]
            )
            self.assertEqual(
                candidate["mention_texts"], [original[a:b] for a, b in candidate["mentions"]]
            )
            allowed_refs = {
                p["id"] for s in payload["units"][candidate["unit"]]["segments"] for p in s["parts"]
            }
            self.assertTrue(
                all(set(refs) <= allowed_refs and refs for refs in candidate["mention_quotes"])
            )
        with self.assertRaisesRegex(ValueError, "POSITIVE_INVALID_QUOTE"):
            validate_response({"relations": {"r0": [1, "b"], "r1": [0]}}, isolated)
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
        self.assertTrue(
            all(classify_rule(doses_only, c).label == "unclear" for c in doses_only.candidates)
        )
        validate_cached(Decision("positive", "model", "", ((0, 5),)), work)
        with self.assertRaisesRegex(ValueError, "POSITIVE_INVALID_CACHE"):
            validate_cached(Decision("positive", "model", "", ((0, len(fallback.text) + 1),)), work)
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
        segments = long_payload["units"]["u0"]["segments"]
        self.assertLessEqual(len(segments), 6)
        self.assertTrue(
            all(sum(len(p["text"]) for p in segment["parts"]) <= 1000 for segment in segments)
        )
        self.assertEqual(
            "".join(p["text"] for segment in segments for p in segment["parts"]), long_text
        )
        seventh_text = "Menta. " * 1000
        seventh_unit = replace(
            long_unit, passage=replace(long_unit.passage, text=seventh_text), end=len(seventh_text)
        )
        seventh_work = (seventh_unit, seventh_unit.candidates[0])
        isolated = pack_batches([seventh_work, seven[0]], config, {1: "menta"}, {10: "Gastrita"})
        self.assertEqual(len(isolated), 2)
        oversized_payload = json.loads(serialize_batch(isolated[0], {1: "menta"}, {10: "Gastrita"}))
        oversized_segments = oversized_payload["units"]["u0"]["segments"]
        self.assertGreater(len(oversized_segments), 6)
        self.assertTrue(
            all(
                sum(len(p["text"]) for p in segment["parts"]) <= 1000
                for segment in oversized_segments
            )
        )
        self.assertEqual(
            "".join(p["text"] for segment in oversized_segments for p in segment["parts"]),
            seventh_text,
        )
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
        client.complete_json.return_value = {"relations": {"r0": [1, "a"]}}
        with (
            patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
            patch("scripts.positive_herb_ranking.make_client", return_value=client),
            redirect_stdout(output),
        ):
            result = run_positive_ranking(config, repository=repository)
        self.assertEqual(result["requests"], 1)
        self.assertEqual({d.label for d in repository.finish.call_args.args[2].values()}, {"mixed"})
        raw_key = cache_key(
            warning_work,
            {**semantic_config(config), "herb_name": "menta", "condition_name": "Gastrita"},
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
        self.assertEqual({d.label for d in repository.finish.call_args.args[2].values()}, {"mixed"})
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
        client.complete_json.return_value = {"relations": {"r0": [1, "a"]}}
        with (
            patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
            patch("scripts.positive_herb_ranking.make_client", return_value=client),
            redirect_stdout(output),
        ):
            result = run_positive_ranking(config, repository=repository)
        self.assertEqual(result["requests"], 1)
        self.assertEqual(len(repository.finish.call_args.args[2]), 2)
        self.assertEqual({d.label for d in repository.finish.call_args.args[2].values()}, {"mixed"})
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
