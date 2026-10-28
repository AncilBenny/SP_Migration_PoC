"""Offline fixture-consistency checks; NOT validation of actual migration output."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ResearchFixtureIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / "examples/research/three-family-traceability.synthetic.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((ROOT / "schema/page.ir.schema.json").read_text(encoding="utf-8"))
        cls.scenarios = cls.fixture["scenarios"]
        cls.kinds = set(cls.schema["$defs"]["node"]["properties"]["kind"]["enum"])

    def test_fixture_is_explicitly_synthetic(self):
        self.assertIs(self.fixture["synthetic"], True)
        self.assertIn("NOT CDPH", self.fixture["disclaimer"])

    def test_three_mvp_families_covered(self):
        self.assertEqual({case["sourceFamily"] for case in self.scenarios},
                         {"modern", "classic-content", "classic-publishing"})
        self.assertEqual({case.get("subtype") for case in self.scenarios if case["sourceFamily"] == "classic-content"},
                         {"classic-wiki", "classic-webpart"})

    def test_mappings_use_existing_ir_kinds_and_provenance(self):
        for case in self.scenarios:
            with self.subTest(case=case["scenarioId"]):
                self.assertTrue(case["expectedMappings"])
                for mapping in case["expectedMappings"]:
                    self.assertIn(mapping["kind"], self.kinds)
                    self.assertTrue(mapping["sourcePath"].startswith("$."))
                    self.assertIn(mapping["fidelity"],
                                  {"exact", "approximate", "unresolved", "unsupported"})
                    self.assertTrue(mapping["note"])

    def test_unsupported_controls_have_diagnostics(self):
        for case in self.scenarios:
            unsupported_paths = {m["sourcePath"] for m in case["expectedMappings"]
                                 if m["kind"] == "unknown"}
            reported_paths = {d["sourcePath"] for d in case["expectedDiagnostics"]}
            self.assertTrue(unsupported_paths.issubset(reported_paths))

    def test_modern_column_width_fractions_reflect_12_grid(self):
        modern = next(case for case in self.scenarios if case["sourceFamily"] == "modern")
        columns = modern["source"]["canvasLayout"]["horizontalSections"][0]["columns"]
        spans = [col["width"] for col in columns]
        self.assertEqual(spans, [8, 4])
        self.assertEqual(sum(spans), 12)
        widths = [m["widthFraction"] for m in modern["expectedMappings"]
                  if m["kind"] == "column"]
        self.assertEqual(len(widths), len(spans))
        for a, b in zip(widths, spans):
            self.assertAlmostEqual(a, b / 12, places=7)

    def test_publishing_example_separates_master_layout_body(self):
        example = next(case for case in self.scenarios
                       if case["sourceFamily"] == "classic-publishing")
        self.assertIn("masterRef", example["source"])
        self.assertIn("layoutRef", example["source"])
        self.assertIn("PublishingPageContent", example["source"]["fields"])
        self.assertTrue(any(m["kind"] == "siteShell" for m in example["expectedMappings"]))


if __name__ == "__main__":
    unittest.main()
