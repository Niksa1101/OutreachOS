"""Central campaign validation — PRD §6.6, DB.md §4.3.

One service decides whether a campaign can be rendered. Issues carry a severity
and optional ``asset_id`` for row-scoped findings. The frontend renders what
this module returns; it must not re-derive rules locally.
"""

from __future__ import annotations

from enum import StrEnum

from outreachos_backend.core.enums import ProbeStatus
from outreachos_backend.modules.video_composer.models import MediaAsset
from outreachos_backend.modules.video_composer.schemas import (
    CampaignValidation,
    ValidationIssue,
)

__all__ = ["validate_campaign"]

_ASPECT_RATIO_16_9 = 16 / 9
_ASPECT_RATIO_TOLERANCE = 0.02


class ValidationIssueCode(StrEnum):
    NO_TALKING_HEAD = "no_talking_head"
    NO_RECORDINGS = "no_recordings"
    SOURCE_FILE_MISSING = "source_file_missing"
    PROBE_FAILED = "probe_failed"
    RECORDING_SHORTER_THAN_TALKING_HEAD = "recording_shorter_than_talking_head"
    ASPECT_RATIO_NOT_16_9 = "aspect_ratio_not_16_9"
    DUPLICATE_COMPANY_NAME = "duplicate_company_name"


class ValidationSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


def _is_16_9(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    return abs((width / height) - _ASPECT_RATIO_16_9) <= _ASPECT_RATIO_TOLERANCE


def _talking_head_duration_ms(asset: MediaAsset) -> int:
    assert asset.trim_start_ms is not None
    assert asset.trim_end_ms is not None
    return max(0, asset.trim_end_ms - asset.trim_start_ms)


def validate_campaign(
    *,
    talking_head: MediaAsset | None,
    recordings: list[MediaAsset],
) -> CampaignValidation:
    """Return typed validation issues and whether Generate may proceed."""

    issues: list[ValidationIssue] = []
    renderable_recording_count = 0

    if talking_head is None:
        issues.append(
            ValidationIssue(
                code=ValidationIssueCode.NO_TALKING_HEAD,
                severity=ValidationSeverity.BLOCKING,
                message="Assign a talking-head video before generating.",
            )
        )
    else:
        if talking_head.file_missing:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.SOURCE_FILE_MISSING,
                    severity=ValidationSeverity.BLOCKING,
                    message="The talking-head source file is missing.",
                    asset_id=talking_head.id,
                )
            )
        elif talking_head.probe_status != ProbeStatus.OK.value:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.PROBE_FAILED,
                    severity=ValidationSeverity.BLOCKING,
                    message=talking_head.probe_error or "The talking-head video could not be read.",
                    asset_id=talking_head.id,
                )
            )

    if not recordings:
        issues.append(
            ValidationIssue(
                code=ValidationIssueCode.NO_RECORDINGS,
                severity=ValidationSeverity.BLOCKING,
                message="Add at least one screen recording before generating.",
            )
        )

    talking_head_duration_ms: int | None = None
    if talking_head is not None and talking_head.probe_status == ProbeStatus.OK.value:
        talking_head_duration_ms = _talking_head_duration_ms(talking_head)

    for recording in recordings:
        if recording.file_missing:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.SOURCE_FILE_MISSING,
                    severity=ValidationSeverity.BLOCKING,
                    message="The source file is missing.",
                    asset_id=recording.id,
                )
            )
            continue

        if recording.probe_status != ProbeStatus.OK.value:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.PROBE_FAILED,
                    severity=ValidationSeverity.BLOCKING,
                    message=recording.probe_error or "That recording could not be read as a video.",
                    asset_id=recording.id,
                )
            )
            continue

        renderable_recording_count += 1

        if (
            talking_head_duration_ms is not None
            and recording.duration_ms is not None
            and recording.duration_ms < talking_head_duration_ms
        ):
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.RECORDING_SHORTER_THAN_TALKING_HEAD,
                    severity=ValidationSeverity.WARNING,
                    message="This recording is shorter than the talking-head clip.",
                    asset_id=recording.id,
                )
            )

        if (
            recording.width is not None
            and recording.height is not None
            and not _is_16_9(recording.width, recording.height)
        ):
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.ASPECT_RATIO_NOT_16_9,
                    severity=ValidationSeverity.WARNING,
                    message="This recording is not 16:9.",
                    asset_id=recording.id,
                )
            )

        if recording.name_auto_suffixed:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.DUPLICATE_COMPANY_NAME,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        "This company name was auto-suffixed because another "
                        "recording already uses it."
                    ),
                    asset_id=recording.id,
                )
            )

    campaign_blockers = [
        issue
        for issue in issues
        if issue.severity == ValidationSeverity.BLOCKING and issue.asset_id is None
    ]
    talking_head_blockers = [
        issue
        for issue in issues
        if issue.severity == ValidationSeverity.BLOCKING
        and issue.asset_id == (talking_head.id if talking_head is not None else None)
    ]

    can_generate = False
    generate_blocked_reason: str | None = None

    if campaign_blockers:
        generate_blocked_reason = campaign_blockers[0].message
    elif talking_head_blockers:
        generate_blocked_reason = talking_head_blockers[0].message
    elif renderable_recording_count == 0:
        if recordings:
            row_blockers = [
                issue
                for issue in issues
                if issue.severity == ValidationSeverity.BLOCKING and issue.asset_id is not None
            ]
            generate_blocked_reason = (
                row_blockers[0].message if row_blockers else "No recordings are ready to render."
            )
        else:
            generate_blocked_reason = "Add at least one screen recording before generating."
    else:
        can_generate = True

    warning_count = sum(1 for issue in issues if issue.severity == ValidationSeverity.WARNING)

    return CampaignValidation(
        issues=issues,
        can_generate=can_generate,
        generate_blocked_reason=generate_blocked_reason,
        renderable_recording_count=renderable_recording_count,
        warning_count=warning_count,
    )
