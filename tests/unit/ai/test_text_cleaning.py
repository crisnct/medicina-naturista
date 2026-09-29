from __future__ import annotations

import unittest

from scripts.clean_documents import clean_text


class CleanTextTests(unittest.TestCase):
    def test_markdown_link_keeps_label_and_drops_url(self):
        text = "Planta [sunătoare](https://example.com/sunatoare) ajută la ficat."

        cleaned = clean_text(text)

        self.assertEqual(cleaned, "Planta sunătoare ajută la ficat.")

    def test_html_anchor_keeps_inner_text_and_drops_href(self):
        text = 'Detalii <a href="https://example.com/x">aici</a> despre remediu.'

        cleaned = clean_text(text)

        self.assertEqual(cleaned, "Detalii aici despre remediu.")

    def test_bare_url_is_removed(self):
        text = "Sursă: https://example.com/articol pentru mai multe informații."

        cleaned = clean_text(text)

        self.assertNotIn("https://", cleaned)
        self.assertIn("Sursă:", cleaned)

    def test_vezi_si_line_is_dropped_entirely(self):
        text = "Dacă apar asemenea simptome, consultați medicul.\nVezi și Piele grasă, Partea a doua.\nUrmătorul paragraf."

        cleaned = clean_text(text)

        self.assertNotIn("Vezi și", cleaned)
        self.assertNotIn("Piele grasă", cleaned)
        self.assertIn("consultați medicul.", cleaned)
        self.assertIn("Următorul paragraf.", cleaned)

    def test_vezi_si_line_with_leading_bullet_marker_is_dropped(self):
        text = "Context anterior.\nQ Vezi și Înțepătură de albine; Alergie la înțepături de insecte\nUrmătorul rând netușat."

        cleaned = clean_text(text)

        self.assertNotIn("Vezi și", cleaned)
        self.assertNotIn("Q ", cleaned)
        self.assertIn("Următorul rând netușat.", cleaned)

    def test_never_changes_the_number_of_lines(self):
        text = (
            "Prima linie [etichetă](http://x.ro) rămâne.\n"
            "Vezi și Altă afecțiune, Partea a doua.\n"
            "https://example.com/doar-link\n"
            "Ultima linie."
        )

        cleaned = clean_text(text)

        self.assertEqual(cleaned.count("\n"), text.count("\n"))

    def test_diacritic_free_vezi_si_is_also_matched(self):
        text = "Vezi si Alergie la polen."

        cleaned = clean_text(text)

        self.assertEqual(cleaned.strip(), "")

    def test_leaves_ordinary_text_unchanged(self):
        text = "Coada-calului ajută la infecții urinare, cf. tradiției populare."

        self.assertEqual(clean_text(text), text)

    def test_strips_emails_and_www_addresses(self):
        cleaned = clean_text("Scrie la ana@exemplu.ro sau vezi www.exemplu.ro/x acum.")

        self.assertNotIn("@", cleaned)
        self.assertNotIn("www", cleaned)

    def test_normalizes_extraction_artefacts_without_touching_newlines(self):
        text = "şi ţ­ară\nﬁer\x00\n"

        cleaned = clean_text(text)

        self.assertEqual(cleaned, "și țară\nfier\n")
        self.assertEqual(cleaned.count("\n"), text.count("\n"))


if __name__ == "__main__":
    unittest.main()
