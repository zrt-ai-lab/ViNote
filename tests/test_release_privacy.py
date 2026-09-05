"""Release scanner classifies synthetic fixtures without suppressing real categories."""
import unittest

from scripts.scan_release import scan_line


class ReleasePrivacyTests(unittest.TestCase):
    def test_url_userinfo_is_not_misclassified_as_company_mail(self):
        self.assertNotIn('company-email', scan_line('fixture.py',
                         'https://fixture:fixture@www.youtube.com/watch?v=fixture'))

    def test_company_mail_in_text_and_url_paths_is_still_detected(self):
        address = 'someone' + '@' + 'company.invalid'
        self.assertIn('company-email', scan_line('fixture.py', address))
        self.assertIn('company-email', scan_line('fixture.py', 'https://example.org/contact/' + address))

    def test_public_example_keys_are_allowed_but_secret_patterns_are_not(self):
        self.assertEqual(scan_line('fixture.py', "api_key='example-key'"), set())
        self.assertEqual(scan_line('fixture.py', "{'api_key': 'example-key'},"), set())
        self.assertEqual(scan_line('fixture.py', 'api_key: Optional[str] = None'), set())
        self.assertEqual(scan_line('fixture.py', 'api_' + 'key = os.getenv("OPENAI_API_KEY")'), set())
        self.assertIn('provider-secret', scan_line('fixture.py', 'sk-' + 'a' * 40))
