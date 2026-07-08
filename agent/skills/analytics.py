"""Skill usage analytics for CowAgent.

Tracks skill usage patterns and generates insights:
- Usage frequency (how often each skill is used)
- Success rate (how reliable each skill is)
- Last used time (identify stale skills)
- Execution time (performance metrics)
- Usage trends (daily/weekly/monthly)

Data is stored in workspace/skills/skill_usage_analytics.json
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

from common.log import logger

# Thread-safe lock for analytics updates
_ANALYTICS_LOCK = threading.Lock()

# Analytics file name
ANALYTICS_FILE = "skill_usage_analytics.json"


def _get_analytics_path(workspace_dir: str) -> Path:
    """Get the path to the analytics file."""
    return Path(workspace_dir) / "skills" / ANALYTICS_FILE


def _load_analytics(workspace_dir: str) -> Dict[str, Any]:
    """Load analytics data from disk."""
    path = _get_analytics_path(workspace_dir)
    if not path.exists():
        return {"skills": {}, "summary": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[SkillAnalytics] Failed to load analytics: {e}")
        return {"skills": {}, "summary": {}}


def _save_analytics(workspace_dir: str, data: Dict[str, Any]) -> None:
    """Save analytics data to disk."""
    path = _get_analytics_path(workspace_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[SkillAnalytics] Failed to save analytics: {e}")


def record_skill_usage(
    workspace_dir: str,
    skill_name: str,
    success: bool,
    execution_time_ms: float = 0.0,
    error_message: str = "",
) -> None:
    """Record a skill usage event.
    
    Args:
        workspace_dir: Workspace directory path
        skill_name: Name of the skill that was used
        success: Whether the skill execution was successful
        execution_time_ms: Execution time in milliseconds
        error_message: Error message if failed
    """
    with _ANALYTICS_LOCK:
        data = _load_analytics(workspace_dir)
        
        # Initialize skill entry if not exists
        if skill_name not in data["skills"]:
            data["skills"][skill_name] = {
                "total_usage": 0,
                "success_count": 0,
                "failure_count": 0,
                "first_used": datetime.now().isoformat(),
                "last_used": None,
                "total_execution_time_ms": 0.0,
                "recent_usage": [],  # Last 100 usage events
            }
        
        skill_data = data["skills"][skill_name]
        
        # Update counters
        skill_data["total_usage"] += 1
        if success:
            skill_data["success_count"] += 1
        else:
            skill_data["failure_count"] += 1
        
        skill_data["last_used"] = datetime.now().isoformat()
        skill_data["total_execution_time_ms"] += execution_time_ms
        
        # Add to recent usage (keep last 100)
        usage_event = {
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "execution_time_ms": execution_time_ms,
        }
        if error_message:
            usage_event["error"] = error_message[:200]  # Truncate long errors
        
        skill_data["recent_usage"].append(usage_event)
        if len(skill_data["recent_usage"]) > 100:
            skill_data["recent_usage"] = skill_data["recent_usage"][-100:]
        
        # Update summary
        _update_summary(data)
        
        _save_analytics(workspace_dir, data)


def _update_summary(data: Dict[str, Any]) -> None:
    """Update the summary statistics."""
    skills = data["skills"]
    
    if not skills:
        data["summary"] = {}
        return
    
    total_usage = sum(s["total_usage"] for s in skills.values())
    total_success = sum(s["success_count"] for s in skills.values())
    
    # Find most/least used
    sorted_by_usage = sorted(skills.items(), key=lambda x: x[1]["total_usage"], reverse=True)
    most_used = sorted_by_usage[0][0] if sorted_by_usage else None
    least_used = sorted_by_usage[-1][0] if sorted_by_usage else None
    
    # Find most/least reliable
    reliable_skills = [
        (name, s["success_count"] / s["total_usage"] if s["total_usage"] > 0 else 0)
        for name, s in skills.items()
    ]
    sorted_by_reliability = sorted(reliable_skills, key=lambda x: x[1], reverse=True)
    most_reliable = sorted_by_reliability[0][0] if sorted_by_reliability else None
    least_reliable = sorted_by_reliability[-1][0] if sorted_by_reliability else None
    
    data["summary"] = {
        "total_skills": len(skills),
        "total_usage": total_usage,
        "overall_success_rate": total_success / total_usage if total_usage > 0 else 0,
        "most_used_skill": most_used,
        "least_used_skill": least_used,
        "most_reliable_skill": most_reliable,
        "least_reliable_skill": least_reliable,
        "last_updated": datetime.now().isoformat(),
    }


def generate_usage_report(
    workspace_dir: str,
    days: int = 30,
    format: str = "text",
) -> str:
    """Generate a skill usage report.
    
    Args:
        workspace_dir: Workspace directory path
        days: Number of days to analyze (default: 30)
        format: Output format - "text", "json", or "markdown"
    
    Returns:
        Formatted report string
    """
    data = _load_analytics(workspace_dir)
    skills = data["skills"]
    
    if not skills:
        return "No skill usage data available yet."
    
    # Filter by time range
    cutoff = datetime.now() - timedelta(days=days)
    filtered_skills = {}
    
    for name, skill_data in skills.items():
        recent = [
            u for u in skill_data["recent_usage"]
            if datetime.fromisoformat(u["timestamp"]) >= cutoff
        ]
        if recent:
            filtered_skills[name] = {
                "total_usage": len(recent),
                "success_count": sum(1 for u in recent if u["success"]),
                "failure_count": sum(1 for u in recent if not u["success"]),
                "avg_execution_time_ms": (
                    sum(u["execution_time_ms"] for u in recent) / len(recent)
                    if recent else 0
                ),
                "last_used": skill_data["last_used"],
            }
    
    if not filtered_skills:
        return f"No skill usage in the last {days} days."
    
    # Sort by usage
    sorted_skills = sorted(
        filtered_skills.items(),
        key=lambda x: x[1]["total_usage"],
        reverse=True
    )
    
    if format == "json":
        return json.dumps({
            "period_days": days,
            "skills": dict(sorted_skills),
            "summary": data.get("summary", {}),
        }, indent=2, ensure_ascii=False)
    
    # Text/Markdown format
    lines = []
    lines.append(f"# Skill Usage Report (Last {days} Days)\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Summary
    total_usage = sum(s["total_usage"] for s in filtered_skills.values())
    total_success = sum(s["success_count"] for s in filtered_skills.values())
    success_rate = (total_success / total_usage * 100) if total_usage > 0 else 0
    
    lines.append("## Summary\n")
    lines.append(f"- **Total Skills Used:** {len(filtered_skills)}")
    lines.append(f"- **Total Usage Count:** {total_usage}")
    lines.append(f"- **Overall Success Rate:** {success_rate:.1f}%")
    lines.append(f"- **Most Used:** {sorted_skills[0][0]} ({sorted_skills[0][1]['total_usage']} times)")
    lines.append("")
    
    # Detailed breakdown
    lines.append("## Detailed Usage\n")
    lines.append("| Skill | Usage | Success Rate | Avg Time (ms) | Last Used |")
    lines.append("|-------|-------|--------------|---------------|-----------|")
    
    for name, stats in sorted_skills:
        success_rate = (stats["success_count"] / stats["total_usage"] * 100) if stats["total_usage"] > 0 else 0
        last_used = stats["last_used"][:10] if stats["last_used"] else "N/A"
        lines.append(
            f"| {name} | {stats['total_usage']} | {success_rate:.1f}% | "
            f"{stats['avg_execution_time_ms']:.1f} | {last_used} |"
        )
    
    lines.append("")
    
    # Identify unused skills (if we have full skill list)
    all_skills = set(skills.keys())
    used_skills = set(filtered_skills.keys())
    unused_skills = all_skills - used_skills
    
    if unused_skills:
        lines.append("## Unused Skills (Recommend for Review)\n")
        for name in sorted(unused_skills):
            last_used = skills[name]["last_used"]
            last_used_str = last_used[:10] if last_used else "Never"
            lines.append(f"- **{name}** - Last used: {last_used_str}")
        lines.append("")
    
    # Performance insights
    slow_skills = [
        (name, stats["avg_execution_time_ms"])
        for name, stats in filtered_skills.items()
        if stats["avg_execution_time_ms"] > 1000  # > 1 second
    ]
    
    if slow_skills:
        lines.append("## Performance Alerts\n")
        lines.append("Skills with average execution time > 1 second:")
        for name, time_ms in sorted(slow_skills, key=lambda x: x[1], reverse=True):
            lines.append(f"- **{name}**: {time_ms:.0f}ms")
        lines.append("")
    
    return "\n".join(lines)


def get_unused_skills(
    workspace_dir: str,
    days: int = 30,
) -> List[str]:
    """Get list of skills not used in the specified time period.
    
    Args:
        workspace_dir: Workspace directory path
        days: Number of days to check
    
    Returns:
        List of unused skill names
    """
    data = _load_analytics(workspace_dir)
    skills = data["skills"]
    
    cutoff = datetime.now() - timedelta(days=days)
    unused = []
    
    for name, skill_data in skills.items():
        last_used = skill_data.get("last_used")
        if not last_used:
            unused.append(name)
            continue
        
        last_used_dt = datetime.fromisoformat(last_used)
        if last_used_dt < cutoff:
            unused.append(name)
    
    return sorted(unused)



