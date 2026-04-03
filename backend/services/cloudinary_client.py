from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from config import settings

try:
    import cloudinary
    import cloudinary.api
    import cloudinary.uploader
    import cloudinary.utils

    HAS_CLOUDINARY_LIB=True
except Exception:
    cloudinary=None
    HAS_CLOUDINARY_LIB=False

LOCAL_PUBLIC_ID_PREFIX="local:"
logger=logging.getLogger("uvicorn.error")


# ---------------- CLOUDINARY ---------------- #

def ensure_cloudinary_configured()->None:
    if not settings.CLOUDINARY_URL:
        raise RuntimeError("Cloudinary is not configured")
    if not HAS_CLOUDINARY_LIB:
        raise RuntimeError("Cloudinary package is not installed")


def upload_pdf(file_bytes:bytes,folder:str,public_id:str)->dict[str,Any]:
    ensure_cloudinary_configured()

    diagnostics=get_cloudinary_diagnostics()
    if not diagnostics["url_valid"]:
        raise RuntimeError("Invalid CLOUDINARY_URL format")

    try:
        _configure_cloudinary_client()

        return cloudinary.uploader.upload(
            file_bytes,
            resource_type="raw",
            folder=folder,
            public_id=public_id,
            format="pdf",
            overwrite=True,
        )
    except Exception as exc:
        logger.exception("Cloudinary upload failed: %s",str(exc)[:200])
        raise RuntimeError(f"Cloudinary upload failed: {str(exc)[:180]}") from exc


# ---------------- LOCAL STORAGE ---------------- #

def save_local_pdf_copy(file_bytes:bytes,folder:str,public_id:str)->str:
    target_path=_local_upload_path(folder,public_id)
    target_path.write_bytes(file_bytes)

    # ✅ Store RELATIVE path instead of absolute
    root=Path(settings.LOCAL_UPLOAD_DIR).resolve()
    relative_path=target_path.relative_to(root)

    return f"{LOCAL_PUBLIC_ID_PREFIX}{relative_path.as_posix()}"


def delete_file(public_id:str)->None:
    if not public_id:
        return

    # Handle local files
    if public_id.startswith(LOCAL_PUBLIC_ID_PREFIX):
        relative_path=public_id[len(LOCAL_PUBLIC_ID_PREFIX):]

        try:
            full_path=Path(settings.LOCAL_UPLOAD_DIR)/relative_path
            full_path.unlink(missing_ok=True)
        except Exception:
            return
        return

    # Handle cloud files
    if not settings.CLOUDINARY_URL or not HAS_CLOUDINARY_LIB:
        return

    try:
        _configure_cloudinary_client()
        cloudinary.uploader.destroy(public_id,resource_type="raw",invalidate=True)
    except Exception:
        return


# ---------------- PATH HELPERS ---------------- #

def _sanitize_folder(folder:str)->Path:
    clean_parts=[]
    for part in folder.replace("\\","/").split("/"):
        token=part.strip()
        if not token or token in {".",".."}:
            continue
        token=re.sub(r"[^a-zA-Z0-9._-]","_",token)
        if token:
            clean_parts.append(token)
    return Path(*clean_parts) if clean_parts else Path()


def _local_upload_path(folder:str,public_id:str)->Path:
    root=Path(settings.LOCAL_UPLOAD_DIR).expanduser().resolve()
    target_dir=(root/_sanitize_folder(folder)).resolve()
    target_dir.mkdir(parents=True,exist_ok=True)

    safe_name=re.sub(r"[^a-zA-Z0-9._-]","_",public_id).strip("._")
    if not safe_name:
        safe_name="upload"

    if not safe_name.lower().endswith(".pdf"):
        safe_name=f"{safe_name}.pdf"

    return target_dir/safe_name


# ---------------- CLOUDINARY CONFIG ---------------- #

def get_cloudinary_diagnostics()->dict[str,Any]:
    raw=(settings.CLOUDINARY_URL or "").strip()

    if not raw:
        return {
            "configured":False,
            "library_available":HAS_CLOUDINARY_LIB,
            "scheme":"",
            "cloud_name":"",
            "has_api_key":False,
            "has_api_secret":False,
            "url_valid":False,
        }

    parsed=urlparse(raw)

    has_api_key=bool(parsed.username)
    has_api_secret=bool(parsed.password)
    cloud_name=parsed.hostname or ""

    valid=(
        parsed.scheme=="cloudinary"
        and has_api_key
        and has_api_secret
        and bool(cloud_name)
    )

    return {
        "configured":True,
        "library_available":HAS_CLOUDINARY_LIB,
        "scheme":parsed.scheme or "",
        "cloud_name":cloud_name,
        "has_api_key":has_api_key,
        "has_api_secret":has_api_secret,
        "url_valid":valid,
    }

def _configure_cloudinary_client()->None:
    raw=(settings.CLOUDINARY_URL or "").strip()
    parsed=urlparse(raw)

    cloudinary.config( # type: ignore
        cloud_name=(parsed.hostname or "").strip(),
        api_key=unquote(parsed.username or ""),
        api_secret=unquote(parsed.password or ""),
        secure=True,
    )


# ---------------- URL BUILDERS ---------------- #

def build_signed_delivery_url(public_id:str|None)->str|None:
    if not public_id:
        return None

    # ✅ LOCAL FILE
    if public_id.startswith(LOCAL_PUBLIC_ID_PREFIX):
        relative_path=public_id[len(LOCAL_PUBLIC_ID_PREFIX):]

        try:
            full_path=Path(settings.LOCAL_UPLOAD_DIR)/relative_path
            return full_path.resolve().as_uri()
        except Exception as exc:
            logger.warning("Local URI error: %s",str(exc)[:100])
            return None

    # ☁️ CLOUDINARY
    if not settings.CLOUDINARY_URL or not HAS_CLOUDINARY_LIB:
        return None

    diagnostics=get_cloudinary_diagnostics()
    if not diagnostics["url_valid"]:
        return None

    try:
        _configure_cloudinary_client()
        signed_url,_=cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="raw",
            type="upload",
            secure=True,
            sign_url=True,
        )
        return signed_url
    except Exception:
        return None


def build_private_download_url(public_id:str|None,file_format:str|None="pdf")->str|None:
    if not public_id:
        return None

    # ✅ LOCAL FILE
    if public_id.startswith(LOCAL_PUBLIC_ID_PREFIX):
        relative_path=public_id[len(LOCAL_PUBLIC_ID_PREFIX):]

        try:
            full_path=Path(settings.LOCAL_UPLOAD_DIR)/relative_path
            return full_path.resolve().as_uri()
        except Exception as exc:
            logger.warning("Local URI error: %s",str(exc)[:100])
            return None

    # ☁️ CLOUDINARY
    if not settings.CLOUDINARY_URL or not HAS_CLOUDINARY_LIB:
        return None

    diagnostics=get_cloudinary_diagnostics()
    if not diagnostics["url_valid"]:
        return None

    try:
        _configure_cloudinary_client()
        return cloudinary.utils.private_download_url(
            public_id=public_id,
            format=file_format,
            resource_type="raw",
            type="upload",
        )
    except Exception:
        return None