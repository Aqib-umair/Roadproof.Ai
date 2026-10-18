from datetime import date
import secrets
import unittest
from unittest.mock import MagicMock

from roadproof.report_views import filter_reports, submission_date
from roadproof.tracking import parse_reference, remember_receipt, resolve_tracking


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.token = secrets.token_urlsafe(32)
        self.report_id = "RP-E84A6867CA"
        self.report = {"id":self.report_id}
        self.db = MagicMock()
        self.db.by_token.side_effect = lambda token: self.report if token == self.token else None

    def test_full_link_and_raw_token_resolve(self):
        for value in [self.token, f'http://localhost:8501/?page=track&token={self.token}',f' ?token={self.token} ']:
            report,token,outcome = resolve_tracking(self.db,value)
            self.assertEqual(report,self.report)
            self.assertEqual(token,self.token)
            self.assertEqual(outcome,"found")

    def test_report_id_without_receipt_never_reads_private_case(self):
        report,token,outcome = resolve_tracking(self.db,self.report_id)
        self.assertIsNone(report)
        self.assertEqual(token,"")
        self.assertEqual(outcome,"id_requires_token")
        self.db.get.assert_not_called()
        self.db.by_token.assert_not_called()

    def test_same_browser_report_id_uses_real_private_token(self):
        for receipts,latest in [({self.report_id:self.token},None),({},dict(id=self.report_id,token=self.token))]:
            report,token,outcome = resolve_tracking(self.db,self.report_id.lower(),receipts,latest)
            self.assertEqual(outcome,"found")
            self.assertEqual(report,self.report)
            self.assertEqual(token,self.token)
        self.db.get.assert_not_called()

    def test_mismatched_saved_token_cannot_open_another_id(self):
        self.db.by_token.return_value = None
        self.db.by_token.side_effect = lambda token:{"id":"RP-AAAAAAAAAA"}
        report,token,outcome = resolve_tracking(self.db,self.report_id,{self.report_id:self.token})
        self.assertIsNone(report)
        self.assertEqual(outcome,"not_found")

    def test_malformed_input_and_duplicate_url_tokens(self):
        for value in ["", "some text", "https://example.test/?page=track",f'https://example.test/?token={self.token}&token={self.token}']:
            self.assertEqual(parse_reference(value)[0],"invalid")
        self.assertEqual(parse_reference(self.report_id)[0],"report_id")

    def test_receipts_preserve_multiple_reports_and_limit_session_memory(self):
        state = {}
        for index in range(25):
            remember_receipt(state,{"id":f"RP-{index:010X}","token":self.token})
        self.assertEqual(len(state["my_reports"]),20)
        self.assertIn("RP-0000000018",state["my_reports"])


class DashboardFilterTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(id="RP-1111111111",location="Citizen road",status="Reported",synthetic=False,created_at="2026-10-18T20:00:00+00:00"),
            dict(id="RP-2222222222",location="Sample road",status="Verification Pending",synthetic=True,created_at="2026-10-18T10:00:00+00:00")]

    def test_new_citizen_cases_visible_by_default_and_searchable(self):
        scoped,filtered = filter_reports(self.rows)
        self.assertEqual(len(filtered),2)
        self.assertEqual(filter_reports(self.rows,query="rp-1111111111")[1],[self.rows[0]])
        self.assertEqual(filter_reports(self.rows,query="citizen")[1],[self.rows[0]])

    def test_scope_and_status_filters_explain_hidden_reports(self):
        self.assertEqual(filter_reports(self.rows,scope="Synthetic samples")[1],[self.rows[1]])
        self.assertEqual(filter_reports(self.rows,scope="Citizen submissions")[1],[self.rows[0]])
        self.assertEqual(filter_reports(self.rows,statuses=["Reported"])[1],[self.rows[0]])

    def test_date_filter_uses_displayed_indian_calendar_day(self):
        self.assertEqual(submission_date(self.rows[0]["created_at"]),date(2026,10,19))
        self.assertEqual(filter_reports(self.rows,dates=(date(2026,10,19),date(2026,10,19)))[1],[self.rows[0]])


if __name__ == "__main__":
    unittest.main()
