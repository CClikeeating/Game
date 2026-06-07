from __future__ import annotations

import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from .schema import SourceBlock, SourceManifest, relative_to
from .utils import IMG_EXTENSIONS, ensure_dir, natural_key


DEFAULT_CHUNK_HEIGHT = 2200
DEFAULT_OVERLAP = 120


def fetch_image(url: str, dest: Path, html_src: Path | None = None) -> None:
    if url.startswith(("http://", "https://")):
        with urllib.request.urlopen(url, timeout=30) as response:
            dest.write_bytes(response.read())
        return
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "" and html_src is not None:
        local_path = (html_src.parent / urllib.parse.unquote(parsed.path)).resolve()
        shutil.copy2(local_path, dest)
        return
    urllib.request.urlretrieve(url, dest)


def split_long_image(
    src: Path,
    output_dir: Path,
    root: Path,
    block_start: int = 1,
    chunk_height: int = DEFAULT_CHUNK_HEIGHT,
    overlap: int = DEFAULT_OVERLAP,
    block_prefix: str = "block",
    kind: str = "image_crop",
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> list[SourceBlock]:
    prepared_dir = output_dir / "prepared_images"
    ensure_dir(prepared_dir)
    blocks: list[SourceBlock] = []
    with Image.open(src) as im:
        im = im.convert("RGB")
        width, height = im.size
        if height <= chunk_height + overlap:
            dest = prepared_dir / f"{block_prefix}_{block_start:04d}.png"
            im.save(dest)
            blocks.append(
                SourceBlock(
                    block_id=f"block_{block_start:04d}",
                    order=block_start,
                    kind=kind,
                    prepared_path=relative_to(dest, root),
                    source_ref=source_ref or str(src),
                    crop_box=[0, 0, width, height],
                    source_size=[width, height],
                    metadata=metadata or {},
                )
            )
            return blocks

        top = 0
        order = block_start
        while top < height:
            bottom = min(height, top + chunk_height)
            crop = im.crop((0, top, width, bottom))
            dest = prepared_dir / f"{block_prefix}_{order:04d}.png"
            crop.save(dest)
            blocks.append(
                SourceBlock(
                    block_id=f"block_{order:04d}",
                    order=order,
                    kind=kind,
                    prepared_path=relative_to(dest, root),
                    source_ref=source_ref or str(src),
                    crop_box=[0, top, width, bottom],
                    source_size=[width, height],
                    overlap_top=overlap if top > 0 else 0,
                    overlap_bottom=overlap if bottom < height else 0,
                    metadata=metadata or {},
                )
            )
            if bottom == height:
                break
            top = bottom - overlap
            order += 1
    return blocks


def prepare_long_image(src: Path, output_dir: Path, root: Path) -> tuple[SourceManifest, list[SourceBlock]]:
    blocks = split_long_image(src, output_dir, root, kind="long_image_crop", source_ref=src.name)
    manifest = SourceManifest(
        source_id=output_dir.name,
        source_type="long_image",
        original_path=str(src),
        output_dir=relative_to(output_dir, root),
        block_count=len(blocks),
        adapter="long_image_adapter",
        notes=["Long image split with vertical overlap for OCR safety."],
    )
    return manifest, blocks


def prepare_html(src: Path, output_dir: Path, root: Path) -> tuple[SourceManifest, list[SourceBlock]]:
    html = src.read_text(encoding="utf-8", errors="ignore")
    urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    download_dir = output_dir / "source_images"
    ensure_dir(download_dir)
    blocks: list[SourceBlock] = []
    order = 1
    for index, url in enumerate(urls, 1):
        suffix = Path(url.split("?")[0]).suffix or ".png"
        downloaded = download_dir / f"html_image_{index:04d}{suffix}"
        fetch_image(url, downloaded, src)
        with Image.open(downloaded) as im:
            _, height = im.size
        if height > DEFAULT_CHUNK_HEIGHT + DEFAULT_OVERLAP:
            blocks.extend(
                split_long_image(
                    downloaded,
                    output_dir,
                    root,
                    block_start=order,
                    kind="html_image_crop",
                    source_ref=downloaded.name,
                    metadata={"source_url": url, "html_image_index": index},
                )
            )
            order = blocks[-1].order + 1
        else:
            prepared = output_dir / "prepared_images" / f"block_{order:04d}{suffix}"
            ensure_dir(prepared.parent)
            shutil.copy2(downloaded, prepared)
            with Image.open(prepared) as im:
                width, height = im.size
            blocks.append(
                SourceBlock(
                    block_id=f"block_{order:04d}",
                    order=order,
                    kind="html_image",
                    prepared_path=relative_to(prepared, root),
                    source_ref=downloaded.name,
                    source_url=url,
                    crop_box=[0, 0, width, height],
                    source_size=[width, height],
                )
            )
            order += 1
    manifest = SourceManifest(
        source_id=output_dir.name,
        source_type="html_image_sequence",
        original_path=str(src),
        output_dir=relative_to(output_dir, root),
        block_count=len(blocks),
        adapter="html_adapter",
        notes=["Images are downloaded and preserved in HTML order."],
    )
    return manifest, blocks


def prepare_pdf(src: Path, output_dir: Path, root: Path) -> tuple[SourceManifest, list[SourceBlock]]:
    import pypdf

    reader = pypdf.PdfReader(str(src))
    text_blocks: list[SourceBlock] = []
    for page_index, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            text_blocks.append(
                SourceBlock(
                    block_id=f"block_{page_index:04d}",
                    order=page_index,
                    kind="pdf_text_page",
                    source_ref=src.name,
                    page=page_index,
                    text=page_text,
                    status="text_extracted",
                    metadata={"page_count": len(reader.pages)},
                )
            )
    if text_blocks:
        manifest = SourceManifest(
            source_id=output_dir.name,
            source_type="text_pdf",
            original_path=str(src),
            output_dir=relative_to(output_dir, root),
            block_count=len(text_blocks),
            adapter="pdf_adapter",
            notes=["PDF has text layer; OCR skipped."],
        )
        return manifest, text_blocks

    prepared_dir = output_dir / "prepared_images"
    ensure_dir(prepared_dir)
    blocks: list[SourceBlock] = []
    order = 1
    for page_index, page in enumerate(reader.pages, 1):
        if not page.images:
            blocks.append(
                SourceBlock(
                    block_id=f"block_{order:04d}",
                    order=order,
                    kind="pdf_page_empty",
                    source_ref=src.name,
                    page=page_index,
                    status="skipped",
                    warnings=["No text layer and no embedded image found on page."],
                )
            )
            order += 1
            continue
        for image_index, image in enumerate(page.images, 1):
            suffix = Path(image.name).suffix or ".png"
            dest = prepared_dir / f"pdf_page_{page_index:04d}_image_{image_index:02d}{suffix}"
            dest.write_bytes(image.data)
            with Image.open(dest) as im:
                width, height = im.size
            metadata = {
                "embedded_image_name": image.name,
                "embedded_image_index": image_index,
                "page_count": len(reader.pages),
            }
            if height > DEFAULT_CHUNK_HEIGHT + DEFAULT_OVERLAP:
                blocks.extend(
                    split_long_image(
                        dest,
                        output_dir,
                        root,
                        block_start=order,
                        kind="pdf_page_image_crop",
                        source_ref=src.name,
                        metadata=metadata,
                    )
                )
                order = blocks[-1].order + 1
                continue
            blocks.append(
                SourceBlock(
                    block_id=f"block_{order:04d}",
                    order=order,
                    kind="pdf_page_image",
                    prepared_path=relative_to(dest, root),
                    source_ref=src.name,
                    page=page_index,
                    crop_box=[0, 0, width, height],
                    source_size=[width, height],
                    metadata=metadata,
                )
            )
            order += 1
    manifest = SourceManifest(
        source_id=output_dir.name,
        source_type="image_pdf",
        original_path=str(src),
        output_dir=relative_to(output_dir, root),
        block_count=len(blocks),
        adapter="pdf_adapter",
        notes=["PDF has no text layer; all embedded page images are prepared for OCR."],
    )
    return manifest, blocks


def prepare_image_folder(src: Path, output_dir: Path, root: Path) -> tuple[SourceManifest, list[SourceBlock]]:
    images = sorted(
        [p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTENSIONS],
        key=natural_key,
    )
    prepared_dir = output_dir / "prepared_images"
    ensure_dir(prepared_dir)
    blocks: list[SourceBlock] = []
    order = 1
    for image in images:
        with Image.open(image) as im:
            _, height = im.size
        if height > DEFAULT_CHUNK_HEIGHT + DEFAULT_OVERLAP:
            blocks.extend(
                split_long_image(
                    image,
                    output_dir,
                    root,
                    block_start=order,
                    kind="folder_image_crop",
                    source_ref=str(image),
                )
            )
            order = blocks[-1].order + 1
            continue
        dest = prepared_dir / f"block_{order:04d}{image.suffix.lower()}"
        shutil.copy2(image, dest)
        with Image.open(dest) as im:
            width, height = im.size
        blocks.append(
            SourceBlock(
                block_id=f"block_{order:04d}",
                order=order,
                kind="folder_image",
                prepared_path=relative_to(dest, root),
                source_ref=str(image),
                crop_box=[0, 0, width, height],
                source_size=[width, height],
            )
        )
        order += 1
    manifest = SourceManifest(
        source_id=output_dir.name,
        source_type="image_folder",
        original_path=str(src),
        output_dir=relative_to(output_dir, root),
        block_count=len(blocks),
        adapter="image_folder_adapter",
        notes=["Images are sorted by natural filename order; order confidence must be reviewed for loose screenshots."],
    )
    return manifest, blocks
