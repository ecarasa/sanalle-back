import re

import boto3

from app.core.config import settings


def _s3_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=settings.S3_ENDPOINT_URL,
    )


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "_", text)


def upload_ingreso_archivo(
    file_bytes: bytes,
    content_type: str,
    proveedor_nombre: str,
    ingreso_numero: str,
    original_filename: str,
) -> tuple[str, str]:
    slug = _slugify(proveedor_nombre) if proveedor_nombre else "sin_proveedor"
    safe_name = re.sub(r"[^\w.\-]", "_", original_filename)
    key = f"{settings.S3_KEY_PREFIX}/{slug}/{ingreso_numero}_{safe_name}"
    _s3_client().put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
        ACL="public-read",
    )
    url = f"{settings.S3_URL}/{key}"
    return key, url


def delete_s3_file(key: str) -> None:
    _s3_client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
