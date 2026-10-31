"""Source-independent interaction evidence and destination tamper-detection."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from poc.behavior_evidence import discover_source_interactions, compare_destination_behavior
from poc.behavior_browser import audit_behavior_browser
from poc.engine import normalize
from poc.mapping import render_target, build_target
from studio.service import ProjectStore

ROOT=Path(__file__).resolve().parents[1]


def source_ir(name):
    doc=json.loads((ROOT/'poc/samples'/name).read_text(encoding='utf-8'))
    return normalize(doc,asset_map=doc.get('_assetMap',{}))


class BehaviorEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ir=source_ir('modern-interactions-synthetic.json')
        cls.profile=json.loads((ROOT/'poc/profiles/client-navigation-filter-demo.json').read_text())

    def test_all_four_approved_interactions_are_static_checked(self):
        h,_,r=render_target(self.ir,self.profile)
        evidence=compare_destination_behavior(self.ir,h,self.profile,r)
        self.assertTrue(evidence['passed'])
        self.assertEqual([x['interaction'] for x in evidence['destinationChecks']], ['toc','tabs','filterLinks'])
        self.assertEqual(evidence['summary']['staticChecksPassed'],3)
        self.assertTrue(all(x['sourceBehaviorVerified'] is False for x in evidence['destinationChecks']))
        self.assertEqual(evidence['sourceBehaviorFidelity'],'unverified-no-observed-sharepoint-interaction-baseline')

    def test_accordion_static_contract_and_no_script_requirement(self):
        p=deepcopy(self.profile)
        p['behaviorMappings']=[{'nodeId':'intro-text','interaction':'accordion'}]
        h,_,r=render_target(self.ir,p)
        result=compare_destination_behavior(self.ir,h,p,r)
        self.assertTrue(result['passed'])
        self.assertNotIn('behavior.js',h)

    def test_source_script_inventory_requires_review_not_autorun(self):
        ir=source_ir('modern-styles-scripts-demo.json')
        evidence=discover_source_interactions(ir)
        script=[x for x in evidence if x['category']=='runtime-evidence']
        self.assertEqual(len(script),1)
        self.assertEqual(script[0]['counts']['externalScripts'],1)
        self.assertEqual(script[0]['counts']['inlineEventHandlers'],1)
        self.assertEqual(script[0]['status'],'review-required')
        self.assertFalse(any(x.get('sourceBehaviorVerified') for x in evidence))
        self.assertTrue(any(x['category']=='unresolved-web-part' for x in evidence))

    def test_structural_candidates_are_not_claimed_original_behaviors(self):
        evidence=discover_source_interactions(self.ir)
        potential=[x for x in evidence if x['category']=='structural-candidate']
        self.assertGreaterEqual(len(potential),3)
        self.assertTrue(all(x['status']=='not-source-behavior-evidence' for x in potential))

    def test_tampered_generated_html_is_detected(self):
        h,_,r=render_target(self.ir,self.profile)
        variants=[
          h.replace('data-behavior="toc"','data-behavior="nothing"'),
          h.replace('class="mig-tab-panel"','class="removed-tab-panel"',1),
          h.replace('data-filter-item','data-broken-item',1),
          h.replace('type="search"','type="text"',1),
          h.replace('<script src="behavior.js" defer></script>',''),
        ]
        for html in variants:
            with self.subTest(length=len(html)):
                result=compare_destination_behavior(self.ir,html,self.profile,r)
                self.assertFalse(result['passed'])
                self.assertGreater(result['summary']['staticChecksFailed'],0)

    def test_missing_mapping_report_fails_closed(self):
        h,_,_=render_target(self.ir,self.profile)
        result=compare_destination_behavior(self.ir,h,self.profile,{})
        self.assertFalse(result['passed'])

    def test_no_mapping_still_records_unresolved_controls(self):
        p=deepcopy(self.profile);p.pop('behaviorMappings')
        h,_,r=render_target(self.ir,p)
        result=r['behaviorEvidence']
        self.assertTrue(result['passed'])
        self.assertEqual(result['summary']['staticChecksPassed'],0)
        self.assertTrue(any(x['category']=='unresolved-web-part' for x in result['sourceEvidence']))

    def test_cli_export_writes_evidence_without_changing_ir(self):
        with TemporaryDirectory() as temp:
            ir_file=Path(temp)/'page.ir.json'
            ir_file.write_text(json.dumps(self.ir,indent=2),encoding='utf-8')
            target=Path(temp)/'target'
            report=build_target(ir_file,ROOT/'poc/profiles/client-navigation-filter-demo.json',target)
            evidence=json.loads((target/'behavior-evidence.json').read_text())
            self.assertEqual(evidence, report['behaviorEvidence'])
            self.assertEqual(ir_file.read_bytes(),(target/'page.ir.json').read_bytes())

    def test_studio_export_contains_behavior_evidence(self):
        store=ProjectStore();project=store.analyze(sample_id='modern-interactions')
        result=store.render(project['projectId'],mode='client',profile=self.profile)
        self.assertTrue(result['mappingReport']['behaviorEvidence']['passed'])
        with ZipFile(BytesIO(store.export(project['projectId'],'client'))) as bundle:
            self.assertIn('behavior-evidence.json',bundle.namelist())
            self.assertEqual(json.loads(bundle.read('behavior-evidence.json'))['summary']['explicitMappings'],3)

    def test_browser_rejects_untrusted_script_or_handlers_without_running(self):
        html,_,r=render_target(self.ir,self.profile)
        for modified in [html+'<script>alert(1)</script>',html.replace('<main>','<main onload="alert(1)">')]:
            with self.subTest(modified=modified[-30:]),self.assertRaisesRegex(ValueError,'BEHAVIOR_UNTRUSTED_BROWSER_INPUT'):
                audit_behavior_browser(self.ir,modified,self.profile,r)


if __name__=='__main__': unittest.main()
