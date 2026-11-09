"""Downloads the inspector's two graph libraries once, so it works offline and loads no code from the internet.

    python3 python/dm/fetch_vendor.py

Each file is checked against a pinned SHA-256 before it is kept. Without them, the pages fall back to the CDN.
"""

import hashlib
import pathlib
import urllib.request

VENDOR = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "vendor"
FILES = {
    "mermaid.min.js": ("https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js",
                       "61b335a46df05a7ce1c98378f60e5f3e77a7fb608a1056997e8a649304a936d6"),
    "svg-pan-zoom.min.js": ("https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js",
                            "f463710320089c61d0f57cec2b886c02de04e21eb92ebd22eaa327fdf0a6b7c6"),
}


def main():
    VENDOR.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in FILES.items():
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit(f"{name}: checksum mismatch, not saved")
        (VENDOR / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes, verified")


if __name__ == "__main__":
    main()
