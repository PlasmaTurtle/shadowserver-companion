"""Compatibility entry points for section policy, status and commands.

New read/guard consumers import reviews.queries; command consumers use
services.reviews. Lower-level components never import this facade.
"""

from .reviews.policy import (
    SECTIONS as SECTIONS,
    FIELDS as FIELDS,
    PREREQUISITES as PREREQUISITES,
    fingerprints as fingerprints,
    assert_current as assert_current,
    changed_paths as changed_paths,
    check_key,
    check_revision,
)
from .reviews.queries import SectionReviewQueries
from .services.reviews import SectionReviewService


class SectionReviews(SectionReviewQueries):
    _check_key = staticmethod(check_key)
    _check_revision = staticmethod(check_revision)

    def validate(self, case_id, key, expected_revision):
        return SectionReviewService(self.store, self).validate(case_id, key, expected_revision)

    def reopen(self, case_id, key, expected_revision, reason):
        return SectionReviewService(self.store, self).reopen(
            case_id, key, expected_revision, reason
        )
