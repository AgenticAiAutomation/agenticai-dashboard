"""Unit tests for the "Path to 80" and passing-checks helpers.

These are pure functions over the scorer's own parameter list, so this suite
needs no database and no running API — which matters, because the failure it
guards against is an exception inside `score_article` taking the whole score
endpoint down with it. Every writer in the dashboard hits that endpoint.

Usage:
    python -m tests.score_path
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.seo.services.scoring import (  # noqa: E402
    PUBLISH_MIN_SCORE, Comment, passing_checks, path_to_threshold)

passed, failed = [], []


def check(name, condition, detail=""):
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}   {detail}")


def param(key, earned, available, implemented=True, group="content"):
    return {
        "key": key, "label": key.replace("_", " ").title(), "group": group,
        "points_earned": earned, "points_available": available,
        "implemented": implemented, "detail": f"detail for {key}",
    }


print("\n1. Degenerate input\n" + "-" * 46)

# A context where every parameter is skipped divides by zero unless guarded.
result = path_to_threshold([], [], earned=0, available=0)
check("no available points does not raise", result["current"] == 0)
check("no available points reports the full gap", result["gap"] == PUBLISH_MIN_SCORE)
check("no available points yields no steps", result["steps"] == [])
check("no available points has no gap marker", result["closes_gap_after"] is None)

check("passing_checks on an empty list is empty", passing_checks([]) == [])

print("\n2. Already at or above the threshold\n" + "-" * 46)

full = [param("a", 50, 50), param("b", 50, 50)]
result = path_to_threshold(full, [], earned=100, available=100)
check("a perfect article scores 100", result["current"] == 100)
check("a perfect article has no gap", result["gap"] == 0)
check("a perfect article needs no steps", result["steps"] == [])
check("the default threshold is the publish gate",
      result["threshold"] == PUBLISH_MIN_SCORE == 80)

# Exactly on the bar is publishable, not one point short of it.
at_bar = [param("a", 80, 100)]
check("exactly at the threshold reports no gap",
      path_to_threshold(at_bar, [], 80, 100)["gap"] == 0)

print("\n3. Normalisation\n" + "-" * 46)

# Half the parameters are skipped, so the denominator is 50, not 100. A raw
# point is worth two score points here — the bug this guards against is
# treating it as one and telling the writer they are twice as close as they are.
partial = [param("a", 40, 50), param("skipped", 0, 50, implemented=False)]
result = path_to_threshold(partial, [], earned=40, available=50)
check("skipped parameters leave the denominator", result["current"] == 80)
check("only implemented parameters become steps", len(result["steps"]) == 1)
check("a raw point is scaled by 100/available",
      result["steps"][0]["score_gain"] == 20.0,
      f'got {result["steps"][0]["score_gain"]}')

print("\n4. Ordering and the gap marker\n" + "-" * 46)

# Scores 73/100 (60 of 82 raw), so the gap is 7. The 12-raw-point fix is worth
# 14.6 on the normalised scale and closes it on its own.
mixed = [
    param("small", 4, 6),      # +2 raw
    param("big", 0, 12),       # +12 raw
    param("medium", 2, 10),    # +8 raw
    param("done", 54, 54),     # already full
]
result = path_to_threshold(mixed, [], earned=60, available=82)
check("steps are ordered by score impact",
      [s["key"] for s in result["steps"]] == ["big", "medium", "small"],
      [s["key"] for s in result["steps"]])
check("parameters at full marks are not steps",
      "done" not in [s["key"] for s in result["steps"]])
check("one sufficient fix closes the gap on its own",
      result["closes_gap_after"] == 1, result["closes_gap_after"])
check("headroom is the sum of every remaining gain",
      abs(result["headroom"] - sum(s["score_gain"] for s in result["steps"])) < 0.05)

# 60/100 with the shortfall spread thin: no single fix is worth the 20 needed,
# so the marker has to walk. This is the case that catches an off-by-one.
spread = [param("a", 0, 15), param("b", 0, 15), param("c", 0, 10),
          param("done", 60, 60)]
result = path_to_threshold(spread, [], earned=60, available=100)
check("the marker walks until the gap is covered",
      result["closes_gap_after"] == 2, result["closes_gap_after"])
check("cumulative gain to the marker covers the gap",
      sum(s["score_gain"] for s in result["steps"][:2]) >= result["gap"])
check("the step before the marker is not enough on its own",
      result["steps"][0]["score_gain"] < result["gap"])

print("\n5. The threshold is always reachable\n" + "-" * 46)

# "available" counts only implemented parameters, so maxing all of them scores
# exactly 100. Headroom is therefore always 100 - current and always covers the
# gap. This pins that invariant: if it ever breaks, the panel needs an
# "unreachable" state that today would be dead code.
for earned_pts, available_pts in [(30, 100), (1, 400), (0, 12), (79, 100)]:
    r = path_to_threshold([param("a", earned_pts, available_pts)], [],
                          earned=earned_pts, available=available_pts)
    check(f"headroom covers the gap at {earned_pts}/{available_pts} raw",
          r["headroom"] >= r["gap"], f'headroom {r["headroom"]} < gap {r["gap"]}')
    check(f"headroom equals 100 - current at {earned_pts}/{available_pts} raw",
          abs(r["headroom"] - (100 - r["current"])) <= 0.6,
          f'headroom {r["headroom"]}, current {r["current"]}')

print("\n6. Fix text from comments\n" + "-" * 46)

comments = [
    Comment(line_number=1, current_text="", suggested_fix="Add 300 words.",
            impact_points=6, parameter="big"),
    Comment(line_number=4, current_text="", suggested_fix="A later duplicate.",
            impact_points=2, parameter="big"),
]
result = path_to_threshold(mixed, comments, earned=60, available=82)
steps = {s["key"]: s for s in result["steps"]}
check("a step carries its parameter's fix text",
      steps["big"]["how"] == "Add 300 words.", steps["big"]["how"])
check("the highest-impact comment wins for a parameter",
      "duplicate" not in steps["big"]["how"])
check("a step without a comment has empty fix text", steps["small"]["how"] == "")
check("every step carries a human-readable group label",
      all(s["group_label"] for s in result["steps"]))

print("\n7. Passing checks\n" + "-" * 46)

results = passing_checks(mixed)
keys = [p["key"] for p in results]
check("only parameters at full marks pass", keys == ["done"], keys)
check("a passing check reports its points", results[0]["points"] == 54)
check("a passing check carries a group label", bool(results[0]["group_label"]))
check("skipped parameters never count as passing",
      passing_checks([param("s", 0, 10, implemented=False)]) == [])
# A skipped parameter has earned == available == 0, which is "full marks" by
# arithmetic alone. Claiming it passes would be a lie to the writer.
check("a skipped zero-point parameter is not passing",
      passing_checks([param("z", 0, 0, implemented=False)]) == [])

print("\n8. The helpers do not mutate the scorer's data\n" + "-" * 46)

before = [param("a", 4, 6), param("b", 0, 12)]
snapshot = [dict(p) for p in before]
path_to_threshold(before, [], earned=4, available=18)
passing_checks(before)
check("parameters are left untouched", before == snapshot)

print("\n" + "=" * 62)
print(f"  {len(passed)} passed, {len(failed)} failed")
print("=" * 62)
sys.exit(1 if failed else 0)
