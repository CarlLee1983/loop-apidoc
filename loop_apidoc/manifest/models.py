from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceFormat(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    WORD = "word"
    #: 舊版二進位 Word(.doc)。與 .docx 分開,因為它們的差別不是版本而是「讀不讀得動」:
    #: OOXML 的驗證／渲染路徑對 OLE 複合檔完全不適用,把兩者塞進同一個值會讓 manifest
    #: 宣稱一件不成立的事(supported),而 operator 要到 source-risk 才發現。
    WORD_LEGACY = "word-legacy"
    #: 試算表(.xlsx/.xls)。與 UNKNOWN 分開的理由和 word-legacy 一樣,而且只有這個
    #: 理由:結果都是拒絕,但認得出格式才講得出下一步。不建轉檔器見 ADR 0012。
    SPREADSHEET = "spreadsheet"
    #: 純文字(.txt)。與 UNKNOWN 分開的理由只有一個:結果都是拒絕,但認得出格式
    #: 才講得出下一步——這裡的下一步是「改副檔名為 .md」,通則講不出這麼具體的事。
    PLAIN_TEXT = "plain-text"
    #: CSV。與 UNKNOWN 分開的理由和 plain-text 一樣,只有這一個:結果都是拒絕,
    #: 但認得出格式才講得出下一步。下一步刻意不是「另存為 CSV」(#98 已否決同一個
    #: 建議,理由是會把 operator 送回這個 unsupported)。
    CSV = "csv"
    OPENAPI_JSON = "openapi-json"
    OPENAPI_YAML = "openapi-yaml"
    HTML = "html"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    UNSUPPORTED = "unsupported"
    DUPLICATE = "duplicate"
    UNREADABLE = "unreadable"
    # Matched an exclude glob: present in the manifest for visibility, but never
    # treated as source evidence.
    IGNORED = "ignored"


class SourceAuthority(str, Enum):
    #: 供應商正式文件。現存的每一份來源都是這個等級 —— 預設值是事實,
    #: 不是相容性妥協。
    NORMATIVE = "normative"
    #: 供應商補充說明的人工摘錄(信件、通訊軟體、另存成 Markdown 的
    #: 試算表)。填得了 `missing`,支撐不了 `explicit_support`;與正式
    #: 文件衝突時正式文件勝。分界線是可重新取得性:這種載體沒有 URL、
    #: 沒有版本,`check-freshness` 無法週期性重走。
    SUPPLEMENTARY = "supplementary"


class LocalSource(BaseModel):
    relative_path: str
    mime_type: str | None
    source_format: SourceFormat
    size_bytes: int = Field(ge=0)
    sha256: str
    scanned_at: datetime
    supported: bool
    status: ProcessingStatus
    duplicate_of: str | None = None
    authority: SourceAuthority = SourceAuthority.NORMATIVE


class UrlSource(BaseModel):
    url: str
    fetched_at: datetime
    http_status: int | None
    content_sha256: str | None = None
    note: str | None = None
    snapshot_file: str | None = None


class Manifest(BaseModel):
    sources_root: str
    generated_at: datetime
    local_sources: list[LocalSource] = Field(default_factory=list)
    url_sources: list[UrlSource] = Field(default_factory=list)

    def readable_local_sources(self) -> list[LocalSource]:
        """支援且可讀的本機來源 —— 擷取實際引用得到的那一組。

        排除 UNSUPPORTED／UNREADABLE(讀不了)、DUPLICATE(與別份逐位元組相同,
        要求重複列出只是噪音)與 IGNORED(依定義從不作為來源證據)。
        """
        return [
            source for source in self.local_sources
            if source.supported and source.status is ProcessingStatus.PENDING
        ]

    def readable_url_sources(self) -> list[UrlSource]:
        """已落地快照的 URL 來源;沒有快照就沒有可讀的東西。"""
        return [source for source in self.url_sources if source.snapshot_file is not None]

    def readable_source_identities(self) -> set[str]:
        """可讀來源的身份字串 —— evidence 的 `source` 與 focus 的
        `searched_sources` 共用同一組詞彙,兩邊不可能各自認定一套。"""
        return (
            {source.relative_path for source in self.readable_local_sources()}
            | {source.url for source in self.readable_url_sources()}
        )

    def all_source_identities(self) -> set[str]:
        """manifest 記載過的每一個來源身份,含讀不到的那些。

        用來分辨「你漏列了可讀來源」與「你列了不存在的來源」:讀不到的來源不
        要求列出,但列了不算錯 —— 那只是多餘,不是捏造。
        """
        return (
            {source.relative_path for source in self.local_sources}
            | {source.url for source in self.url_sources}
        )

    def unsupported(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.UNSUPPORTED]

    def duplicates(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.DUPLICATE]

    def unreadable(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.UNREADABLE]
