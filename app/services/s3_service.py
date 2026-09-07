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
) -> str:
    slug = _slugify(proveedor_nombre) if proveedor_nombre else "sin_proveedor"
    safe_name = re.sub(r"[^\w.\-]", "_", original_filename)
    key = f"{settings.S3_KEY_PREFIX}/{slug}/{ingreso_numero}_{safe_name}"
    # Sin ACL público: una factura de proveedor no debería quedar accesible por
    # URL a quien la adivine. El objeto queda privado y se sirve con un link
    # prefirmado y temporal desde `url_prefirmada`.
    _s3_client().put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


def delete_s3_file(key: str) -> None:
    _s3_client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)


def url_prefirmada(key: str, expira_segundos: int = 300) -> str:
    """Link temporal de descarga para un objeto privado. Vale unos minutos."""
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expira_segundos,
    )


def key_de(archivo_ref: str) -> str:
    """La key del objeto. Acepta registros viejos que guardaron la URL completa."""
    if archivo_ref.startswith("http"):
        # Formato viejo: `${S3_URL}/${key}` o URL absoluta del bucket.
        if settings.S3_URL and archivo_ref.startswith(f"{settings.S3_URL}/"):
            return archivo_ref[len(settings.S3_URL) + 1:]
        return archivo_ref.split("/", 3)[-1]
    return archivo_ref
