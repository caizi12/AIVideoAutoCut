# -*- coding: utf-8 -*-
"""生成补画面素材来源清单。"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from backend.config.paths import PROJECT_ROOT


def collect_broll_sources(session: Dict) -> List[Dict]:
    """从 broll_session 中收集已选素材来源。"""
    sources = []
    seen = set()
    for shot in (session or {}).get('shots') or []:
        selected_id = shot.get('selected_candidate_id') or ''
        candidates = shot.get('candidates') or []
        selected = None
        if selected_id:
            selected = next((item for item in candidates if item.get('candidate_id') == selected_id), None)
        if not selected:
            selected = next((item for item in candidates if item.get('local_path')), None)
        if not selected:
            continue

        key = (selected.get('provider'), selected.get('source_id'), selected.get('source_url'))
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            'shot_id': shot.get('shot_id') or '',
            'subtitle_text': shot.get('subtitle_text') or '',
            'provider': selected.get('provider') or '',
            'source_id': selected.get('source_id') or '',
            'source_url': selected.get('source_url') or '',
            'author': selected.get('author') or '',
            'license': selected.get('license') or '',
            'license_url': selected.get('license_url') or '',
            'query': selected.get('query') or '',
            'local_path': selected.get('local_path') or ''
        })
    return sources


def write_license_manifest(project_id: str, session: Dict) -> Dict:
    """写出 JSON 来源清单，返回文件路径和访问 URL。"""
    manifest_dir = PROJECT_ROOT / 'output' / 'broll'
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / f'broll_sources_{project_id}.json'
    payload = {
        'project_id': project_id,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'sources': collect_broll_sources(session)
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return {
        'path': str(path),
        'url': f'/output/broll/{path.name}',
        'sources': payload['sources']
    }
