"""ServiceNow draft payload builder (mocked, no external calls)."""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Dict, List, Tuple, Optional


def build(alarm: Dict, validation: List[Dict], context_meta: Dict, insights: Optional[Dict] = None) -> Tuple[Dict, str]:
    short_description = f"Alarm {alarm.get('alarm_id')} {alarm.get('symptom')} on {alarm.get('device')} ({alarm.get('site')})"
    # Basic impact/urgency heuristic
    severity = (alarm.get('severity') or '').lower()
    impact = urgency = 3
    if severity in ('critical', 'major'):
        impact = urgency = 2
    if severity in ('critical',) and any(r.get('label') == 'target' and r.get('status') == 'FAIL' for r in validation):
        impact = urgency = 1

    attachments = []
    for k in ('diagram', 'diagram_overlay', 'prior_incidents', 'config'):
        if k in context_meta:
            attachments.append(context_meta[k])

    payload = {
        'number': None,
        'short_description': short_description[:160],
        'description': f"Symptom: {alarm.get('symptom')}\nSite: {alarm.get('site')}\nDevice: {alarm.get('device')}\nIP: {alarm.get('ip')}\nSeverity: {alarm.get('severity')}\nTimestamp: {alarm.get('timestamp')}",
        'category': 'network',
        'impact': impact,
        'urgency': urgency,
        'cmdb_ci': alarm.get('device'),
        'location': alarm.get('site'),
        'attachments': attachments,
        'alarm_id': alarm.get('alarm_id'),
        'severity': alarm.get('severity'),
        'site': alarm.get('site'),
        'device': alarm.get('device'),
        'ip': alarm.get('ip'),
        'timestamp': alarm.get('timestamp'),
    'generated_at': datetime.now(UTC).isoformat(),
    }
    if insights:
        payload['insights'] = insights

    # Markdown summary
    lines = [f"# ServiceNow Draft: {alarm.get('alarm_id')}", '', short_description, '', '## Validation Results']
    for r in validation:
        lines.append(f"- {r['label']} ({r['ip']}): {r.get('status')} loss={r.get('loss_pct')}% rtt={r.get('rtt_ms')}ms")
    if attachments:
        lines += ['', '## Attachments', *[f"- {a}" for a in attachments]]
    if insights:
        lines += ['', '## Blast Radius', f"- Scope: {insights.get('scope')}", f"- Why: {insights.get('reason')}"]
        if insights.get('next_steps'):
            lines += ['', '## Suggested Next Steps']
            for step in insights['next_steps']:
                lines.append(f"- {step}")
    markdown = '\n'.join(lines) + '\n'
    return payload, markdown

__all__ = ["build"]
