"""Proof that Veridex is not just shouting 'scam' at everything.
Runs a licensed firm, the same firm with scam tricks, and a made-up firm, and prints the verdicts side by side.
Run:  python tools/legit_test.py            (add a real link:  python tools/legit_test.py https://real-firm-website)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("VERIDEX_DB", os.path.join(os.path.dirname(__file__), "..", "test_only.db"))
from core import checker
extra = sys.argv[1] if len(sys.argv) > 1 else ""
CASES = [
 ("A. Real firm, plain question", f"Is Fincap Securities Ltd licensed? {extra}"),
 ("B. Real firm name + scam tricks (someone copying them)", "Fincap Securities guaranteed 30% weekly, send registration fee to MoMo 0244556781 today only"),
 ("C. Firm the SEC named as unlicensed", "Invest with Qumatix, 20% weekly"),
 ("D. Name we have never heard of", "Please tell me about Zorbex Holdings"),
]
for title, text in CASES:
    v = checker.check(text)
    print("=" * 70); print(title); print("Input:", text); print("Verdict:", v.level, "|", v.headline)
    for i, l in v.checks: print("  ", i, l)
    print("  Why:", v.reasons[0] if v.reasons else "")
