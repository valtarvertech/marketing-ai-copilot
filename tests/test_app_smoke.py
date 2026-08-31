"""
UI smoke test: every navigation section should render without raising an
exception. This uses Streamlit's AppTest harness to actually run app.py
and click through the sidebar, rather than just checking that the
process starts (which only exercises the default page).
"""

import pytest
from streamlit.testing.v1 import AppTest

SECTIONS = [
    "Executive Overview",
    "Performance Intelligence",
    "Campaign Intelligence",
    "Keyword Intelligence",
    "Search Term Intelligence",
    "Budget Pacing",
    "Competitive Intelligence",
    "Change Intelligence",
    "Optimization Center",
    "Ask My Account",
]


@pytest.mark.parametrize("section", SECTIONS)
def test_section_renders_without_exception(section):
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value(section).run()
    assert not at.exception, f"{section} raised: {[str(e) for e in at.exception]}"
