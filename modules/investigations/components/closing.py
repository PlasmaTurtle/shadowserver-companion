"""Compatible closing API with rendering and workflow in separate modules."""

from .closing_renderers import (
    display_time as display_time,
    sections as sections,
    render_closing as render_closing,
)
from .services.closures import closing_data as closing_data, close_case as publish_closing
from .services.recovery import recover_closings as recover_closings


def close_case(store, case_id, values):
    return publish_closing(store, case_id, values, render_closing=render_closing)
