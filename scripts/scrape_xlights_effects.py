#!/usr/bin/env python3
"""Scrape xLights effect parameters from GitHub C++ source files.

One-time dev tool to extract parameter names, types, defaults, and ranges
from the xLights effects source code. Output is raw JSON to stdout for
hand-review before incorporation into builtin_effects.json.

Usage:
    python scripts/scrape_xlights_effects.py > raw_effects.json
    python scripts/scrape_xlights_effects.py --effect Fire  # single effect
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
import urllib.error
from typing import Any

BASE_URL = (
    "https://raw.githubusercontent.com/xLightsSequencer/xLights/"
    "master/xLights/effects/"
)

# Map effect display name -> C++ filename stem (without "Effect.cpp/h")
EFFECT_FILE_MAP: dict[str, str] = {
    "On": "On",
    "Off": "Off",
    "Color Wash": "ColorWash",
    "Fill": "Fill",
    "Shimmer": "Shimmer",
    "Strobe": "Strobe",
    "Twinkle": "Twinkle",
    "Bars": "Bars",
    "Butterfly": "Butterfly",
    "Circles": "Circles",
    "Curtain": "Curtain",
    "Fan": "Fan",
    "Marquee": "Marquee",
    "Pinwheel": "Pinwheel",
    "Plasma": "Plasma",
    "Ripple": "Ripple",
    "Shape": "Shape",
    "Shockwave": "Shockwave",
    "Spirals": "Spirals",
    "Wave": "Wave",
    "Fire": "Fire",
    "Fireworks": "Fireworks",
    "Liquid": "Liquid",
    "Meteors": "Meteors",
    "Snowflakes": "Snowflakes",
    "Tree": "Tree",
    "Tendril": "Tendril",
    "Single Strand": "SingleStrand",
    "Morph": "Morph",
    "Warp": "Warp",
    "Music": "Music",
    "VU Meter": "VUMeter",
    "Text": "Text",
    "Pictures": "Pictures",
    "Kaleidoscope": "Kaleidoscope",
}


def fetch_file(filename: str) -> str | None:
    """Fetch a file from the xLights GitHub repo. Returns content or None."""
    url = BASE_URL + filename
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "xlight-scraper/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  WARN: {filename} -> HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  WARN: {filename} -> {e}", file=sys.stderr)
        return None


def extract_defines(header_src: str) -> dict[str, int | float]:
    """Extract #define constants with _MIN, _MAX, _DIVISOR suffixes."""
    defines: dict[str, int | float] = {}
    pattern = re.compile(
        r"#define\s+([\w]+(?:_MIN|_MAX|_DIVISOR|_DEFAULT))\s+(-?[\d.]+)"
    )
    for m in pattern.finditer(header_src):
        name = m.group(1)
        val_str = m.group(2)
        try:
            defines[name] = int(val_str)
        except ValueError:
            defines[name] = float(val_str)
    return defines


def extract_storage_names(cpp_src: str, header_src: str) -> list[str]:
    """Extract E_SLIDER_*, E_CHECKBOX_*, E_CHOICE_*, E_TEXTCTRL_* names."""
    combined = (cpp_src or "") + "\n" + (header_src or "")
    pattern = re.compile(r'\b(E_(?:SLIDER|CHECKBOX|CHOICE|TEXTCTRL|VALUECURVE)_\w+)')
    names = sorted(set(pattern.findall(combined)))
    return names


def extract_get_calls(cpp_src: str) -> list[dict[str, Any]]:
    """Extract parameter info from GetValueCurveInt, GetValueCurveDouble, etc."""
    params: list[dict[str, Any]] = []

    # GetValueCurveInt("ParamName", default, SettingsMap, ...)  or
    # GetValueCurveInt("ParamName", default, min, max, ...)
    int_pattern = re.compile(
        r'GetValueCurveInt\(\s*"([^"]+)"\s*,\s*(-?[\d.]+)\s*,'
    )
    for m in int_pattern.finditer(cpp_src):
        params.append({
            "call": "GetValueCurveInt",
            "param_name": m.group(1),
            "default": m.group(2),
            "supports_value_curve": True,
        })

    # GetValueCurveDouble
    dbl_pattern = re.compile(
        r'GetValueCurveDouble\(\s*"([^"]+)"\s*,\s*(-?[\d.]+)\s*,'
    )
    for m in dbl_pattern.finditer(cpp_src):
        params.append({
            "call": "GetValueCurveDouble",
            "param_name": m.group(1),
            "default": m.group(2),
            "supports_value_curve": True,
        })

    # SettingsMap.GetBool("E_CHECKBOX_...")
    bool_pattern = re.compile(
        r'(?:SettingsMap|settings)[\.\->]*GetBool\(\s*"([^"]+)"(?:\s*,\s*(true|false|0|1))?\s*\)'
    )
    for m in bool_pattern.finditer(cpp_src):
        params.append({
            "call": "GetBool",
            "param_name": m.group(1),
            "default": m.group(2) if m.group(2) else "false",
            "supports_value_curve": False,
        })

    # SettingsMap.Get("E_CHOICE_...", "default")
    get_pattern = re.compile(
        r'(?:SettingsMap|settings)[\.\->]*Get\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*\)'
    )
    for m in get_pattern.finditer(cpp_src):
        name = m.group(1)
        # Only capture E_ prefixed names (skip buffer/color settings)
        if name.startswith("E_"):
            params.append({
                "call": "Get",
                "param_name": name,
                "default": m.group(2),
                "supports_value_curve": False,
            })

    # SettingsMap.GetInt("E_SLIDER_...", default)
    getint_pattern = re.compile(
        r'(?:SettingsMap|settings)[\.\->]*GetInt\(\s*"([^"]+)"\s*,\s*(-?[\d]+)\s*\)'
    )
    for m in getint_pattern.finditer(cpp_src):
        name = m.group(1)
        if name.startswith("E_"):
            params.append({
                "call": "GetInt",
                "param_name": name,
                "default": m.group(2),
                "supports_value_curve": False,
            })

    # SettingsMap.GetFloat("E_TEXTCTRL_...", default)
    getfloat_pattern = re.compile(
        r'(?:SettingsMap|settings)[\.\->]*GetFloat\(\s*"([^"]+)"\s*,\s*(-?[\d.]+)\s*\)'
    )
    for m in getfloat_pattern.finditer(cpp_src):
        name = m.group(1)
        if name.startswith("E_"):
            params.append({
                "call": "GetFloat",
                "param_name": name,
                "default": m.group(2),
                "supports_value_curve": False,
            })

    return params


def extract_choice_options(cpp_src: str, header_src: str) -> dict[str, list[str]]:
    """Try to extract choice dropdown options from source.

    Looks for patterns like:
        Choice_X->Append("Option1");
        or string comparisons against CHOICE parameters
    """
    options: dict[str, list[str]] = {}
    combined = (cpp_src or "") + "\n" + (header_src or "")

    # Look for string comparisons: == "value" near CHOICE parameter names
    choice_names = re.findall(r'E_CHOICE_(\w+)', combined)
    for cname in set(choice_names):
        # Find string values compared against this choice
        vals_pattern = re.compile(
            rf'(?:E_CHOICE_{re.escape(cname)}|{re.escape(cname.split("_")[-1])})'
            r'[^;]*?==\s*"([^"]+)"',
        )
        found = vals_pattern.findall(combined)
        if found:
            options[f"E_CHOICE_{cname}"] = sorted(set(found))

    return options


def infer_widget_type(storage_name: str) -> str:
    """Infer widget type from storage name prefix."""
    if "_SLIDER_" in storage_name:
        return "slider"
    elif "_CHECKBOX_" in storage_name:
        return "checkbox"
    elif "_CHOICE_" in storage_name:
        return "choice"
    elif "_TEXTCTRL_" in storage_name:
        return "textctrl"
    elif "_VALUECURVE_" in storage_name:
        return "textctrl"
    return "unknown"


def scrape_effect(effect_name: str, file_stem: str) -> dict[str, Any]:
    """Scrape a single effect and return raw extracted data."""
    print(f"Scraping {effect_name} ({file_stem}Effect.cpp/h)...", file=sys.stderr)

    cpp_src = fetch_file(f"{file_stem}Effect.cpp")
    header_src = fetch_file(f"{file_stem}Effect.h")

    result: dict[str, Any] = {
        "effect_name": effect_name,
        "file_stem": file_stem,
        "cpp_found": cpp_src is not None,
        "header_found": header_src is not None,
        "defines": {},
        "storage_names": [],
        "get_calls": [],
        "choice_options": {},
    }

    if header_src:
        result["defines"] = extract_defines(header_src)

    if cpp_src or header_src:
        result["storage_names"] = extract_storage_names(cpp_src or "", header_src or "")
        result["choice_options"] = extract_choice_options(cpp_src or "", header_src or "")

    if cpp_src:
        result["get_calls"] = extract_get_calls(cpp_src)

    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Scrape xLights effect parameters")
    parser.add_argument(
        "--effect",
        type=str,
        default=None,
        help="Scrape a single effect by display name (e.g., 'Fire')",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: True)",
    )
    args = parser.parse_args()

    if args.effect:
        if args.effect not in EFFECT_FILE_MAP:
            print(f"Unknown effect: {args.effect}", file=sys.stderr)
            print(f"Available: {', '.join(sorted(EFFECT_FILE_MAP))}", file=sys.stderr)
            sys.exit(1)
        effects_to_scrape = {args.effect: EFFECT_FILE_MAP[args.effect]}
    else:
        effects_to_scrape = EFFECT_FILE_MAP

    results: dict[str, Any] = {}
    for name, stem in effects_to_scrape.items():
        results[name] = scrape_effect(name, stem)

    # Summary stats
    found = sum(1 for r in results.values() if r["cpp_found"])
    total_params = sum(len(r["storage_names"]) for r in results.values())
    print(
        f"\nDone: {found}/{len(results)} .cpp files found, "
        f"{total_params} total storage names extracted",
        file=sys.stderr,
    )

    indent = 2 if args.pretty else None
    json.dump(results, sys.stdout, indent=indent, default=str)
    print()  # trailing newline


if __name__ == "__main__":
    main()
