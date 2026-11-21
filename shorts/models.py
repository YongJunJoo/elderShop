"""데이터 구조: 상품 입력과 Claude가 만드는 쇼츠 대본."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Product(BaseModel):
    """products/*.json 한 개. 사람이 고르거나 상품 선정 단계가 채운다."""

    slug: str = Field(description="폴더 이름으로 쓸 영문 식별자, 예: bath-safety-mat")
    name: str
    category: str
    price_krw: Optional[int] = None
    affiliate_url: Optional[str] = Field(None, description="쿠팡 파트너스 등 제휴 링크")
    images: List[str] = Field(default_factory=list, description="상품 이미지 경로 또는 URL")
    review_notes: str = Field(
        "",
        description="공개 리뷰에서 모은 장점·불만 메모. 비어 있으면 웹 검색으로 채운다.",
    )


SceneKind = Literal["hook", "criteria", "pros", "cons", "avoid", "cta"]


class Scene(BaseModel):
    kind: SceneKind
    caption: str = Field(description="화면에 크게 띄울 자막. 한 줄 12자 이내, 최대 2줄(줄바꿈은 \\n)")
    narration: str = Field(description="TTS로 읽을 문장. 쉬운 말, 짧은 문장")


class ShortScript(BaseModel):
    product_name: str
    title: str = Field(description="유튜브 제목, 40자 이내, #shorts 제외")
    description: str = Field(description="설명란. 광고 고지 문구를 첫 줄에 포함")
    hashtags: List[str]
    scenes: List[Scene]
    source_notes: List[str] = Field(description="장점·불만의 근거가 된 출처 요약(검수용, 영상에 안 나감)")
    approved: bool = Field(False, description="사람이 검수 후 true로 바꾼다")
