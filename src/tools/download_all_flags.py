from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

DEFAULT_URL = "https://flagcdn.com/40x30/{code}.png"
DEFAULT_CACHE_DIR = Path("data/flags")
CHUNK_SIZE = 8192
USER_AGENT = "SectorFlowDrive/FlagCacheV1"

ISO_ALPHA2_CODES = [
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR",
    "AS", "AT", "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE",
    "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ",
    "BR", "BS", "BT", "BV", "BW", "BY", "BZ", "CA", "CC", "CD",
    "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN", "CO", "CR",
    "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI",
    "FJ", "FK", "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF",
    "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS",
    "GT", "GU", "GW", "GY", "HK", "HM", "HN", "HR", "HT", "HU",
    "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR", "IS", "IT",
    "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK",
    "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME",
    "MF", "MG", "MH", "MK", "ML", "MM", "MN", "MO", "MP", "MQ",
    "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA",
    "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR", "NU",
    "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS",
    "RU", "RW", "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI",
    "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS", "ST", "SV",
    "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK",
    "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW", "TZ", "UA",
    "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
]


def normalize_codes(codes: Iterable[str]) -> list[str]:
    result: list[str] = []
    for code in codes:
        clean = str(code or "").strip().upper()
        if len(clean) == 2 and clean.isalpha():
            result.append(clean)
    return sorted(set(result))


def download_flag(code: str, url_template: str, target_dir: Path) -> bool:
    url = url_template.format(code=code.lower(), CODE=code.upper())
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / f"{code.lower()}.png"
    if destination.exists() and destination.stat().st_size > 0:
        print(f"SKIP {code}: already exists")
        return True

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read()
            if not content.startswith(b"\x89PNG\r\n\x1a\n"):
                print(f"FAIL {code}: invalid PNG")
                return False
            destination.write_bytes(content)
            print(f"OK   {code}: {len(content)} bytes")
            return True
    except urllib.error.HTTPError as exc:
        print(f"FAIL {code}: HTTP {exc.code}")
    except urllib.error.URLError as exc:
        print(f"FAIL {code}: URL error {exc.reason}")
    except ssl.SSLError as exc:
        print(f"FAIL {code}: SSL error {exc}")
    except socket.timeout:
        print(f"FAIL {code}: timeout")
    except OSError as exc:
        print(f"FAIL {code}: os error {exc}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download all country flag PNGs to the local data/flags cache."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Flag provider URL template (default: %(default)s)",
    )
    parser.add_argument(
        "--destination",
        default=str(DEFAULT_CACHE_DIR),
        help="Destination directory for flag images",
    )
    parser.add_argument(
        "--codes",
        nargs="*",
        help="Optional list of ISO alpha-2 country codes to download",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Download the full embedded ISO alpha-2 code list.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.15,
        help="Delay in seconds between downloads",
    )
    args = parser.parse_args()

    target_dir = Path(args.destination)
    codes = []
    if args.codes:
        codes = normalize_codes(args.codes)
    elif args.include_all:
        codes = normalize_codes(ISO_ALPHA2_CODES)
    else:
        codes = normalize_codes(ISO_ALPHA2_CODES)

    if not codes:
        print("Nenhum código válido informado.")
        return 1

    success = 0
    total = len(codes)
    for index, code in enumerate(codes, start=1):
        print(f"[{index}/{total}] {code}")
        if download_flag(code, args.url, target_dir):
            success += 1
        time.sleep(max(0.0, float(args.delay)))

    print(f"Downloaded {success}/{total} flags to {target_dir}")
    return 0 if success == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
