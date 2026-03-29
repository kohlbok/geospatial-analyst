import io
import logging
import zipfile

import requests

from ..config import DATA_RAW

log = logging.getLogger(__name__)


def _download_file(url, dest, description="file"):
    if dest.exists() and dest.stat().st_size > 0:
        log.info(f"{description} already cached at {dest}")
        return True
    log.info(f"Downloading {description} from {url}")
    try:
        resp = requests.get(url, timeout=300, stream=True, allow_redirects=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info(f"Downloaded {description} ({dest.stat().st_size} bytes)")
        return True
    except Exception as e:
        log.warning(f"Failed to download {description}: {e}")
        return False


def _download_and_extract_zip(url, dest_dir, description="archive"):
    dest_dir.mkdir(parents=True, exist_ok=True)
    marker = dest_dir / ".downloaded"
    if marker.exists():
        log.info(f"{description} already extracted at {dest_dir}")
        return True
    log.info(f"Downloading {description} from {url}")
    try:
        resp = requests.get(url, timeout=600, stream=True)
        resp.raise_for_status()
        content = io.BytesIO(resp.content)
        with zipfile.ZipFile(content) as zf:
            zf.extractall(dest_dir)
        marker.touch()
        log.info(f"Extracted {description} to {dest_dir}")
        return True
    except Exception as e:
        log.warning(f"Failed to download {description}: {e}")
        return False
