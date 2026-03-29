"""
Auto-install Playwright Chromium browser on first use.

Eliminates the manual `uv run playwright install chromium` step.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

_install_lock = threading.Lock()
_installed = False


def ensure_chromium() -> None:
    """Install Chromium browser if not already present. Safe to call repeatedly."""
    global _installed
    if _installed:
        return

    with _install_lock:
        if _installed:
            return

        try:
            from playwright._impl._driver import compute_driver_executable
            driver = compute_driver_executable()
        except Exception:
            driver = None

        # Check if chromium is already installed by looking for the browser
        if driver:
            try:
                result = subprocess.run(
                    [str(driver), "install", "--dry-run", "chromium"],
                    capture_output=True, text=True, timeout=10,
                )
                # If dry-run succeeds without "will download", it's already installed
                if result.returncode == 0 and "will download" not in result.stdout.lower():
                    _installed = True
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

        # Install chromium
        logger.info("Playwright Chromium not found — installing automatically...")
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min max
            )
            _installed = True
            logger.info("Playwright Chromium installed successfully.")
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to install Playwright Chromium: %s", exc.stderr)
            raise RuntimeError(
                "Could not auto-install Playwright Chromium. "
                "Run manually: uv run playwright install chromium"
            ) from exc
        except subprocess.TimeoutExpired:
            logger.error("Playwright Chromium install timed out after 5 minutes.")
            raise RuntimeError("Playwright Chromium install timed out.")
