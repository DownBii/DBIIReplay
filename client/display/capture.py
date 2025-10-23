"""Capture device auto-selection helper.

This script queries Windows for PnP/Camera devices via PowerShell and picks a
likely capture-card device name using keyword scoring. If `config.json` has
"source": "capture" and lacks `device`, the chosen device is written back
into `config.json`.

Improvements: safer PowerShell queries (use -Property Name -Match), Get-CimInstance
where available, and a ffmpeg DirectShow fallback. Deduplicates and scores
device names.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import List, Optional, Tuple


def project_root() -> str:
    # capture.py is in client/display/ so project root is two levels up
    return os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))


def config_path() -> str:
    return os.path.join(project_root(), 'config.json')


def _run_powershell(command: str, timeout: float = 6.0) -> str:
    completed = subprocess.run(
        ['powershell', '-NoProfile', '-Command', command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (completed.stdout or '').strip()


def _run_cmd(cmd: List[str], timeout: float = 6.0) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or '').strip(), (proc.stderr or '').strip()


def find_capture_devices_pnp() -> List[str]:
    """Use PowerShell (CIM/PnP) queries to gather friendly device names."""
    candidates: List[str] = []
    filter_keywords = 'Elgato|Blackmagic|AVerMedia|Hauppauge|Capture|HDMI|USB|Camera|Cam'
    # Prefer Get-CimInstance if present (works on newer PowerShell/Windows)
    ps_cmd = (
        "Get-CimInstance Win32_PnPEntity | Where-Object -Property Name -Match '" + filter_keywords + "' | Select-Object -ExpandProperty Name"
    )
    try:
        out = _run_powershell(ps_cmd)
        if out:
            candidates = [line.strip() for line in out.splitlines() if line.strip()]
            return list(dict.fromkeys(candidates))
    except Exception:
        pass

    # Try Get-PnpDevice which can list cameras on some systems
    try:
        out = _run_powershell("Get-PnpDevice -Class Camera | Select-Object -ExpandProperty FriendlyName")
        if out:
            candidates = [line.strip() for line in out.splitlines() if line.strip()]
            return list(dict.fromkeys(candidates))
    except Exception:
        pass

    # Last resort: list all PnP names, filter in Python
    try:
        out = _run_powershell("Get-CimInstance Win32_PnPEntity | Select-Object -ExpandProperty Name")
        if out:
            all_names = [line.strip() for line in out.splitlines() if line.strip()]
            keywords = ['elgato', 'blackmagic', 'avermedia', 'hauppauge', 'capture', 'hdmi', 'usb', 'camera', 'cam']
            for name in all_names:
                nl = name.lower()
                if any(k in nl for k in keywords):
                    candidates.append(name)
            return list(dict.fromkeys(candidates))
    except Exception:
        pass

    return []


def find_capture_devices_ffmpeg() -> List[str]:
    """Fallback: call ffmpeg to enumerate DirectShow devices (video/audio)."""
    devices: List[str] = []
    cmds = [
        ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
    ]
    for cmd in cmds:
        try:
            rc, out, err = _run_cmd(cmd, timeout=8.0)
            text = out + '\n' + err
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                # ffmpeg typically prints device entries in quotes
                if line.startswith('"') and line.endswith('"'):
                    devices.append(line.strip('"'))
                    continue
                if '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 3:
                        name = parts[1].strip()
                        if name:
                            devices.append(name)
        except Exception:
            continue
    return list(dict.fromkeys(devices))


def find_capture_devices() -> List[str]:
    pnp = find_capture_devices_pnp()
    if pnp:
        return pnp
    return find_capture_devices_ffmpeg()


def score_device_name(name: str) -> int:
    n = name.lower()
    score = 0
    weights = [
        ('elgato', 50), ('blackmagic', 50), ('avermedia', 45), ('hauppauge', 45),
        ('capture', 30), ('video', 40), ('hdmi', 25), ('usb', 10), ('webcam', 12), ('camera', 5), ('cam', 4),
    ]
    for k, w in weights:
        if k in n:
            score += w
    if len(n) > 20:
        score += 2
    return score


def choose_best_device(devices: List[str]) -> Optional[str]:
    if not devices:
        return None
    scored = sorted(((score_device_name(d), d) for d in devices), reverse=True)
    best_score, best_name = scored[0]
    return best_name


def load_config(path: Optional[str] = None) -> dict:
    p = path or config_path()
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict, path: Optional[str] = None) -> None:
    p = path or config_path()
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


def ensure_default_capture_device(dry_run: bool = False) -> Optional[str]:
    cfg = load_config()
    if not isinstance(cfg, dict):
        return None
    if cfg.get('source') != 'capture':
        return None
    if cfg.get('device'):
        return cfg.get('device')
    devices = find_capture_devices()
    best = choose_best_device(devices)
    if best:
        cfg['device'] = best
        if not dry_run:
            save_config(cfg)
        return best
    return None


if __name__ == '__main__':
    chosen = ensure_default_capture_device()
    if chosen:
        print(f"Wrote device '{chosen}' into config.json")
        sys.exit(0)
    else:
        print("No likely capture device found or config.source != 'capture'. No changes made.")
        sys.exit(2)

