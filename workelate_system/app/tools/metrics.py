from app.tools.registry import register


"""
Metrics generation tool.

What it does:
- Returns KPI definitions and analytics structure
- Placeholder for real analytics integration
Main purpose:
Provide structured performance metrics.
"""

@register("metrics_generate")
async def metrics_generate(**kwargs) -> dict:
    """
    Generate metrics + dashboards.
    Goal-aware: if task_goal is provided, tailor outputs to that domain.
    If goal is missing/empty, return a clarify-style metrics object instead of guessing.
    """
    task_goal = str(kwargs.get("task_goal") or "").strip()
    stage = str(kwargs.get("stage") or "growth").strip()

    if not task_goal:
        return {
            "error": "missing_task_goal",
            "note": "Provide task_goal to generate domain-specific KPIs without guessing.",
            "required_inputs": ["task_goal", "stage (optional)", "activation_event (optional)"],
        }

    goal_low = task_goal.lower()

    # --- fitness / coaching-ish heuristic ---
    if any(x in goal_low for x in ["fitness", "workout", "coaching", "trainer", "nutrition", "health"]):
        return {
            "task_goal": task_goal,
            "stage": stage,
            "north_star_metric": "weekly_active_coached_users",
            "funnel": ["signup", "onboarding_complete", "first_plan_created", "first_workout_logged", "subscription_start"],
            "metrics": {
                "weekly_active_coached_users": {
                    "definition": "Users who logged at least 1 workout OR completed 1 coaching check-in in the last 7 days",
                    "formula": "count_distinct(user_id where event in {workout_logged, checkin_completed} in last_7d)",
                    "primary_events": ["workout_logged", "checkin_completed"],
                },
                "plan_creation_rate": {
                    "definition": "Share of new users who create a workout plan within 48 hours",
                    "formula": "users_plan_created_48h / new_signups",
                    "primary_events": ["signup", "plan_created"],
                },
                "workout_completion_rate": {
                    "definition": "Share of scheduled workouts that get completed",
                    "formula": "completed_workouts / scheduled_workouts",
                    "primary_events": ["workout_scheduled", "workout_completed"],
                },
                "streak_7d": {
                    "definition": "Users with a 7-day activity streak",
                    "formula": "count_distinct(user_id with >=1 activity each day for 7 days)",
                    "primary_events": ["app_open", "workout_logged", "checkin_completed"],
                },
                "retention_d7": {
                    "definition": "Users active on day 7 after signup",
                    "formula": "users_active_day_7 / users_active_day_0",
                    "primary_events": ["app_open", "workout_logged"],
                },
                "subscription_conversion_rate": {
                    "definition": "Share of activated users who start subscription",
                    "formula": "subscribers_started / activated_users",
                    "primary_events": ["subscription_started", "payment_succeeded"],
                },
            },
            "event_tracking_schema": {
                "user_id": "string",
                "event_name": "string",
                "timestamp": "datetime",
                "properties": {
                    "device": "string",
                    "plan": "string",
                    "source": "string",
                    "workout_type": "string",
                    "duration_min": "number",
                },
            },
            "recommended_dashboards": [
                {
                    "name": "Engagement & Progress",
                    "tiles": [
                        "Weekly active coached users",
                        "Workouts completed per user per week",
                        "Streak distribution (0–7+ days)",
                        "Plan creation rate (48h)",
                    ],
                },
                {
                    "name": "Retention",
                    "tiles": [
                        "D1/D7/D30 cohorts",
                        "Churn rate",
                        "Session frequency",
                    ],
                },
                {
                    "name": "Revenue (if applicable)",
                    "tiles": [
                        "Subscriber growth",
                        "Trial → paid conversion",
                        "ARPU",
                    ],
                },
            ],
            "implementation_note": "Map these events to your analytics stack (GA4/Segment/Mixpanel/Amplitude).",
            "inputs_seen": list(kwargs.keys()),
        }

    # --- default generic (but still grounded to task_goal text) ---
    return {
        "task_goal": task_goal,
        "stage": stage,
        "north_star_metric": "activation_rate",
        "metrics": {
            "activation_rate": {
                "definition": "Percentage of new users who complete the key activation event",
                "formula": "activated_users / new_signups",
                "primary_events": ["signup", "activation_event"],
            },
            "retention_d7": {
                "definition": "Users returning 7 days after first activity",
                "formula": "users_active_day_7 / users_active_day_0",
                "primary_events": ["app_open", "session_start"],
            },
        },
        "note": "This is a generic fallback. Provide more domain detail (activation_event, core actions) for sharper KPIs.",
        "inputs_seen": list(kwargs.keys()),
    }


