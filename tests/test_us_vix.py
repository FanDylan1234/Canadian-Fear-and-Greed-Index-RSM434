import io
import tempfile
import unittest
from pathlib import Path
from fgindex.us_vix import refresh_vix, decode_history

class VixTests(unittest.TestCase):
    def test_timeout_uses_cboe_close_and_excludes_future(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise TimeoutError("FRED timed out")
            return io.BytesIO(b"DATE,OPEN,HIGH,LOW,CLOSE\n11/09/2026,99,100,98,20\n11/10/2026,99,100,98,21\n11/11/2026,99,100,98,22\n")
        with tempfile.TemporaryDirectory() as folder:
            result = refresh_vix(folder, "2026-11-09", "2026-11-10", opener)
            self.assertEqual(result["provider"], "Cboe")
            text = (Path(folder)/"fred_vix.csv").read_text()
            self.assertIn("2026-11-10,21.0", text)
            self.assertNotIn("2026-11-11", text)
            self.assertTrue((Path(folder)/"us-vix-source.json").exists())

    def test_failures_do_not_replace_cache(self):
        for payload in (b"<html>error</html>", b"DATE,CLOSE\n11/10/2026,21\n",
                        b"DATE,CLOSE\n11/09/2026,nan\n11/10/2026,21\n"):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"fred_vix.csv"
                original = "observation_date,VIXCLS\n2026-11-09,20\n2026-11-10,21\n"
                path.write_text(original)
                def opener(request, timeout):
                    if "fred.stlouisfed.org" in request.full_url:
                        raise TimeoutError()
                    return io.BytesIO(payload)
                with self.assertRaises(RuntimeError):
                    refresh_vix(folder, "2026-11-09", "2026-11-10", opener)
                self.assertEqual(path.read_text(), original)

    def test_fred_success_does_not_call_fallback(self):
        def opener(request, timeout):
            self.assertIn("fred.stlouisfed.org", request.full_url)
            return io.BytesIO(b"observation_date,VIXCLS\n2026-11-10,21\n")
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(refresh_vix(folder, "2026-11-10", "2026-11-10", opener)["provider"], "FRED")

    def test_duplicate_dates_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            decode_history("DATE,CLOSE\n11/10/2026,20\n11/10/2026,21\n", "Cboe", "2026-11-01", "2026-11-10")
