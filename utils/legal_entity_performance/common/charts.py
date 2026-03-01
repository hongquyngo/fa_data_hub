# utils/legal_entity_performance/common/charts.py
"""
Common chart utilities for Legal Entity Performance.
Aligned with kpi_center_performance/common/charts.py
"""

import altair as alt
import pandas as pd


def empty_chart(message: str = "No data available") -> alt.Chart:
    """Return an empty chart with a message."""
    return alt.Chart(pd.DataFrame({'text': [message]})).mark_text(
        fontSize=14, color='#999999'
    ).encode(
        text='text:N'
    ).properties(width='container', height=100)
