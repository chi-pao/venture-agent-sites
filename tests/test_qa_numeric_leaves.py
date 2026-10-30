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

    def test_only_native_view_defaults_feed_time_arithmetic(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                page.set_content('<form id="recordForm"><input id="recordMinutes" type="number" value="99"></form><input id="start" type="time" value="09:30"><input id="end" type="time" value="17:00"><input id="pause" type="number" value="45"><input id="secret" type="password" value="never-copy"><input id="text" value="not-a-numeric-default">')
                defaults=app.qa_capture_view_input_defaults(page)
                self.assertEqual(defaults,{'#start':'09:30','#end':'17:00','#pause':'45'})
                rule=dict(metric='duration',where='inputs',start_input='#start',end_input='#end',break_input='#pause')
                self.assertEqual(app.qa_evaluate_projection([],rule,dict(input_values=defaults)),'405')
            finally:browser.close()

    def test_browser_hour_minute_format_keeps_zero_padded_remainder(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.set_content('<div><span>使える稼働時間</span><strong id="time">7時間00分</strong></div>')
                formats=app.capture_qa_display_contracts(page)
                self.assertEqual(formats['#time']['number_widths'],[0,2])
                rule=dict(metric='duration',start_input='#start',end_input='#end',break_input='#pause')
                clock=dict(input_values={'#start':'09:00','#end':'17:05','#pause':'60'})
                values=[app.qa_evaluate_projection([],dict(metric='time_component',component=component,source_rule=rule),clock) for component in ('hours','minutes')]
                expected=app.qa_compile_bound_primary(dict(exact_check=dict(op='text_equals',selector='#time',expected_values=values,expected_literals=['','時間','分'])),'#time',formats)
                self.assertEqual(expected['exact_check']['value'],'7時間05分')
                page.locator('#time').evaluate('(node)=>node.textContent="7時間05分"')
                self.assertEqual(page.locator('#time').inner_text(),expected['exact_check']['value'])
            finally:browser.close()
