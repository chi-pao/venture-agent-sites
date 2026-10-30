"""Actual Chromium format/selector regression; not generated-product acceptance."""
import unittest
from playwright.sync_api import sync_playwright
from test_preview import app


class NumericLeafBrowserTests(unittest.TestCase):
    def test_anonymous_currency_and_count_leaves_keep_exact_labels_and_grouping(self):
        source='<div id="totals"><div class="kpi"><span>未完了</span><strong>2件</strong></div><div class="kpi"><span>返金予定の合計</span><strong>¥8,000</strong></div></div>'
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.set_content(source)
                formats=app.capture_qa_display_contracts(page)
                leaf='#totals > div:nth-child(2) > strong:nth-child(2)'
                self.assertEqual(page.locator(leaf).inner_text(),'¥8,000')
                self.assertEqual(formats[leaf]['label'],'返金予定の合計')
                self.assertEqual(formats[leaf]['slots'],1)
                self.assertEqual(formats[leaf]['template'],'¥{n0}')
                self.assertEqual(formats['#totals']['slots'],2)
                inventory=app.qa_merge_display_inventory(app.compact_qa_inventory(source),formats)
                self.assertTrue(any(n['selector']==leaf for n in inventory['outputs']))
                expected=app.qa_compile_bound_primary(dict(exact_check=dict(op='text_equals',selector=leaf,expected_values=['12000'],expected_literals=['¥',''])),leaf,formats)
                self.assertEqual(expected['exact_check']['value'],'¥12,000')
                page.locator(leaf).evaluate('(node)=>node.textContent="¥12,000"')
                self.assertEqual(page.locator(leaf).inner_text(),expected['exact_check']['value'])
            finally:browser.close()
