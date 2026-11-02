import importlib.util
import pathlib
import unittest
spec = importlib.util.spec_from_file_location('generator', pathlib.Path(__file__).parents[1]/'generate_tashkil.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

class GeneratorTests(unittest.TestCase):
    def test_overlay_preserves_punctuation_whitespace_and_spelling(self):
        source = 'قال،  أحمد: العلم\nنور.'
        result = g.overlay(source, 'قَالَ أَحْمَدُ الْعِلْمُ نُورٌ')
        self.assertEqual(g.bare(result), source)
        self.assertIn('،  ',result)
        self.assertIn('\n',result)

    def test_rejects_changed_letters(self):
        with self.assertRaises(ValueError): g.overlay('علم', 'عَمَلٌ')

    def test_existing_vowels_and_protected_passage(self):
        self.assertEqual(g.overlay('عِلْم', 'عَلَمٌ', [(0,5)]), 'عِلْم')
        self.assertTrue(g.overlay('عِلْم', 'عَلَمٌ').startswith('عِل'))

    def test_quoted_and_quran_matching_spans_are_protected(self):
        source = "قال: 'كل حزب بما لديهم فرحون' ثم شرح."
        spans = g.protected_spans(source, {('كل','حزب','بما'), ('بما','لديهم','فرحون')})
        start = source.index('كل')
        end = source.index('فرحون') + len('فرحون')
        self.assertTrue(all(any(a <= i < b for a,b in spans) for i in range(start,end)))

    def test_chunks_roundtrip(self):
        source = 'الف باء،\n' * 100
        self.assertEqual(''.join(s for _,s in g.chunks(source)), source)

if __name__ == '__main__': unittest.main()
