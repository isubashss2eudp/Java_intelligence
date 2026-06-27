from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional


class JavaFileMetadata(BaseModel):
    """
    Metadata extracted from a single Java source file.
    Does NOT store raw content - content is read on-demand
    from file_path during chunking to keep metadata.json small.
    """

    file_path: str

    package: Optional[str] = None

    imports: List[str] = []

    annotations: List[str] = []

    classes: List[str] = []

    interfaces: List[str] = []

    enums: List[str] = []

    methods: List[str] = []

    lines_of_code: int = 0

    content_hash: str = ""
