# -*- coding: utf-8 -*-
"""数据模型：每个数字都必须是一个可定位、可复核的证据单元。"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class Company(BaseModel):
    code: str
    name: str
    short_name: str = ''


class Quality(BaseModel):
    status: Literal['pass', 'warning', 'fail'] = 'pass'
    checks: List[str] = Field(default_factory=list)
    messages: List[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """六元组：公司、期间、指标、数值、单位、来源页码 + 原文片段。"""

    evidence_id: str
    company: Company
    report_date: str = ''
    announce_date: str = ''
    evidence_level: Literal['verified', 'structured'] = 'verified'
    source_type: Literal['annual_report_pdf', 'structured_api'] = 'annual_report_pdf'
    source_url: Optional[str] = None
    period: str
    metric: str
    metric_name: str
    value: Optional[float] = None
    prior_value: Optional[float] = None
    unit: str = '元'
    page: Optional[int] = None
    printed_page: Optional[int] = None
    snippet: str
    bbox: Optional[BBox] = None
    source_file: str
    statement: str
    item_raw: str
    note: Optional[str] = None
    value_type: Literal['disclosed', 'computed'] = 'disclosed'
    zero_type: Optional[Literal['零', '未披露', '不适用']] = None
    formula: Optional[str] = None
    inputs: Optional[List[str]] = None
    quality: Quality = Field(default_factory=Quality)
    subject_check: Quality = Field(default_factory=Quality)


class Ratio(BaseModel):
    ratio: str
    name: str
    company: Company
    period: str
    value: Optional[float] = None
    unit: str = '%'
    formula: str
    value_type: Literal['disclosed', 'computed'] = 'computed'
    inputs: List[Dict[str, Any]]
    evidence: List[str]
    quality: Quality = Field(default_factory=Quality)


class CheckResult(BaseModel):
    check: str
    status: Literal['pass', 'warning', 'fail']
    detail: str
    left: Optional[float] = None
    right: Optional[float] = None
    diff: Optional[float] = None
    evidence: List[str] = Field(default_factory=list)


class DatasetMeta(BaseModel):
    company: Company
    period: str
    report_date: str = ''
    announce_date: str = ''
    dataset_id: str = ''
    evidence_level: Literal['verified', 'structured'] = 'verified'
    source_type: Literal['annual_report_pdf', 'structured_api'] = 'annual_report_pdf'
    source_url: Optional[str] = None
    source_file: str
    source_sha256: str
    page_count: int
    extracted_at: str
    statements: List[str]
    fact_count: int
    row_count: int
    coverage_score: float = 0.0
    coverage: Dict[str, Any] = Field(default_factory=dict)
    quality_gate: str = ''


class RawRow(BaseModel):
    page: int
    statement: str
    item: str
    note: Optional[str] = None
    value: Optional[float] = None
    prior_value: Optional[float] = None
    snippet: str
    bbox: Optional[BBox] = None
    complete: bool = True
