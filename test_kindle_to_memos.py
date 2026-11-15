"""Tests for the parsing and formatting logic. Run with: python -m unittest -v"""

import unittest

import kindle_to_memos as k

SAMPLE = """﻿Political Philosophy of AI, The - Mark Coeckelbergh (Mark Coeckelbergh)
- Your Highlight on page 120 | Location 2385-2386 | Added on Tuesday, October 13, 2026 9:39:03 AM

Through our performances with the technology, we also make ourselves into data as we technoperformatively constitute our selves on social media and elsewhere.
==========
Violence (Big Ideas) (Zizek, Slavoj)
- Your Highlight on page 206 | Location 2700-2702 | Added on Friday, June 30, 2023 8:56:08 AM

If one means by violence a radical upheaval of the basic social relations, then, crazy and tasteless as it may sound, the problem with historical monsters who slaughtered millions was that they were not violent enough. Sometimes, doing nothing is the most violent thing to do.
==========
Political Philosophy of AI, The - Mark Coeckelbergh (Mark Coeckelbergh)
- Your Bookmark on page 120 | Location 2387 | Added on Tuesday, October 13, 2026 9:39:58 AM

==========
Confessions of an Economic Hit Man, 3rd Edition (Perkins, John)
- Your Highlight on page 1 | Location 185-186 | Added on Saturday, July 1, 2023 8:02:17 AM

the exploitation of resources to satisfy short-term materialistic consumption and increase the riches and power of a few elites.

==========
Decolonising the Mind - James Currey (James Currey)
- Your Highlight on page 103 | Location 2325-2333 | Added on Saturday, March 14, 2026 2:22:54 PM

The other line identifies with the tradition of resistance in all the nationalities. It sees #1 priority in the people.
==========
The Message (Coates, Ta-Nehisi)
- Your Bookmark on page 143 | Location 1328 | Added on Wednesday, November 12, 2025 12:58:33 PM

==========
"""


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.clippings = k.parse_clippings(SAMPLE)

    def test_bookmarks_are_skipped(self):
        self.assertEqual(len(self.clippings), 4)
        self.assertTrue(all(c.kind == "Highlight" for c in self.clippings))

    def test_new_format_title_and_author(self):
        c = self.clippings[0]
        self.assertEqual(c.title, "Political Philosophy of AI, The")
        self.assertEqual(c.author, "Mark Coeckelbergh (Mark Coeckelbergh)")
        self.assertEqual(c.page, "120")
        self.assertEqual(c.location, "2385-2386")

    def test_old_format_author_in_parentheses(self):
        c = self.clippings[1]
        self.assertEqual(c.title, "Violence (Big Ideas)")
        self.assertEqual(c.author, "Zizek, Slavoj")

    def test_old_format_with_edition_in_title(self):
        c = self.clippings[2]
        self.assertEqual(c.title, "Confessions of an Economic Hit Man, 3rd Edition")
        self.assertEqual(c.author, "Perkins, John")

    def test_new_format_with_dash_in_author_block(self):
        c = self.clippings[3]
        self.assertEqual(c.title, "Decolonising the Mind")
        self.assertEqual(c.author, "James Currey (James Currey)")

    def test_tags(self):
        self.assertEqual(
            self.clippings[0].tags,
            ["clippings", "Political-Philosophy-of-AI-The", "Mark-Coeckelbergh-Mark-Coeckelbergh"],
        )
        self.assertEqual(self.clippings[1].tags, ["clippings", "Violence-Big-Ideas", "Zizek-Slavoj"])

    def test_empty_clipping_is_skipped(self):
        raw = "Some Book (Someone)\n- Your Highlight on page 1 | Location 5 | Added on X\n\n"
        self.assertEqual(k.parse_clippings(raw), [])


class FormatTests(unittest.TestCase):
    def test_hashtags_in_text_are_escaped(self):
        clipping = k.parse_clippings(SAMPLE)[3]
        content = k.format_memo(clipping)
        self.assertIn(r"\#1 priority", content)

    def test_memo_contains_tags_and_key_marker(self):
        clipping = k.parse_clippings(SAMPLE)[0]
        content = k.format_memo(clipping)
        self.assertIn("#clippings #Political-Philosophy-of-AI-The #Mark-Coeckelbergh-Mark-Coeckelbergh", content)
        self.assertIn(f"<!-- kindle-key:{clipping.key} -->", content)


class DeduplicationTests(unittest.TestCase):
    def test_key_is_stable_and_whitespace_insensitive(self):
        a = k.parse_clippings(SAMPLE)[0]
        b = k.Clipping(a.title, a.author, a.kind, a.location, a.page, "  " + a.text.replace(" ", "  ") + "\n")
        self.assertEqual(a.key, b.key)

    def test_existing_and_repeated_clippings_are_removed(self):
        clippings = k.parse_clippings(SAMPLE)
        existing = {clippings[0].key}
        result = k.deduplicate(clippings + [clippings[1]], existing)
        self.assertEqual([c.title for c in result], ["Violence (Big Ideas)", "Confessions of an Economic Hit Man, 3rd Edition", "Decolonising the Mind"])

    def test_key_marker_is_recognised(self):
        clipping = k.parse_clippings(SAMPLE)[0]
        match = k.KEY_MARKER_RE.search(k.format_memo(clipping))
        self.assertEqual(match.group(1), clipping.key)


if __name__ == "__main__":
    unittest.main()
