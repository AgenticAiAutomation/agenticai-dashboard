"""Target-reach-date projection.

    avg_daily_gain = mean(historical_daily_progress)
    if avg_daily_gain <= 0 -> "on hold - no forward progress detected"
    else days_remaining = (target - current) / avg_daily_gain
    projected_date = today + days_remaining

Confidence comes from the standard deviation of the daily series, propagated
into a +/- day interval on the projected date.
"""
import statistics
from datetime import date, timedelta
from typing import List, Optional

from app.seo.schemas import TargetProjection


def project_target_date(
    label: str,
    current_value: float,
    target_value: float,
    historical_daily_progress: List[float],
    amber_after_weeks: int = 1,
    red_after_weeks: int = 2,
    deadline: Optional[date] = None,
    today: Optional[date] = None,
) -> TargetProjection:
    today = today or date.today()
    remaining = target_value - current_value

    if remaining <= 0:
        return TargetProjection(
            label=label,
            current_value=current_value,
            target_value=target_value,
            avg_daily_gain=None,
            projected_date=today,
            confidence_days=0,
            days_remaining=0,
            status="achieved",
            message=f"Target already met ({current_value:g} of {target_value:g}).",
        )

    series = [float(x) for x in historical_daily_progress]
    avg_daily_gain = statistics.fmean(series) if series else 0.0

    if avg_daily_gain <= 0:
        return TargetProjection(
            label=label,
            current_value=current_value,
            target_value=target_value,
            avg_daily_gain=avg_daily_gain,
            projected_date=None,
            confidence_days=None,
            days_remaining=None,
            status="on_hold",
            message="on hold — no forward progress detected",
        )

    days_remaining = remaining / avg_daily_gain
    # Cap at ~5 years so a near-zero velocity cannot overflow date arithmetic.
    days_remaining = min(days_remaining, 1825.0)
    projected = today + timedelta(days=round(days_remaining))

    # Propagate the volatility of the daily series onto the date estimate:
    # a one-sigma swing in velocity moves the finish line by this many days.
    if len(series) > 1:
        stdev = statistics.stdev(series)
        low_rate = max(avg_daily_gain - stdev, 1e-6)
        high_rate = avg_daily_gain + stdev
        slow_days = min(remaining / low_rate, 1825.0)
        fast_days = remaining / high_rate
        confidence_days = int(round(max(slow_days - days_remaining,
                                        days_remaining - fast_days)))
    else:
        confidence_days = None

    status, message = _classify(
        projected, deadline, days_remaining, amber_after_weeks, red_after_weeks,
        confidence_days,
    )

    return TargetProjection(
        label=label,
        current_value=current_value,
        target_value=target_value,
        avg_daily_gain=round(avg_daily_gain, 4),
        projected_date=projected,
        confidence_days=confidence_days,
        days_remaining=int(round(days_remaining)),
        status=status,
        message=message,
    )


def _classify(projected, deadline, days_remaining, amber_weeks, red_weeks, confidence_days):
    suffix = f" (±{confidence_days} days)" if confidence_days is not None else ""
    if deadline is None:
        return "on_track", f"Projected {projected.isoformat()}{suffix} at current velocity."

    slip_days = (projected - deadline).days
    if slip_days <= 0:
        return "on_track", (
            f"Projected {projected.isoformat()}{suffix}, "
            f"{abs(slip_days)} days ahead of the {deadline.isoformat()} deadline."
        )
    if slip_days <= amber_weeks * 7:
        return "slipping", (
            f"Projected {projected.isoformat()}{suffix} — {slip_days} days past "
            f"the {deadline.isoformat()} deadline."
        )
    if slip_days <= red_weeks * 7:
        return "slipping", (
            f"Projected {projected.isoformat()}{suffix} — {slip_days} days behind. "
            "Velocity needs to increase."
        )
    return "at_risk", (
        f"Projected {projected.isoformat()}{suffix} — {slip_days} days behind the "
        f"{deadline.isoformat()} deadline. Current velocity will not reach the target."
    )


def daily_deltas(cumulative: List[float]) -> List[float]:
    """Convert a running total series into per-day gains."""
    return [cumulative[i] - cumulative[i - 1] for i in range(1, len(cumulative))]
