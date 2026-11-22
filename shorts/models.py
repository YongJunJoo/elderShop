"""데이터 구조: 상품 입력과 Claude가 만드는 쇼츠 대본."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Product(BaseModel):
    """상품 한 개. 사람이 고르거나 상품 선정 단계가 채운다."""

    slug: str = Field(description="폴더 이름으로 쓸 영문 식별자, 예: bath-safety-mat")
    name: str
    category: str
    price_krw: Optional[int] = None
    link_no: Optional[int] = Field(None, description="프로필 링크 모음 페이지의 상품 번호 (CTA: 프로필 링크 N번)")
    affiliate_url: Optional[str] = Field(None, description="쿠팡 파트너스 등 제휴 링크")
    images: List[str] = Field(default_factory=list, description="상세페이지 이미지 경로 또는 URL, 4~8장 권장")
    review_notes: str = Field("", description="공개 리뷰에서 모은 장점·불만 메모. 비어 있으면 웹 검색으로 채운다.")
    image_source: Optional[dict] = Field(None, description="images 단계가 사진을 가져온 출처(검수용)")


class Bundle(BaseModel):
    """TOP3 묶음 영상용. products/*.json 에 {"slug": ..., "products": [...]} 형태로 둔다."""

    slug: str
    theme: str = Field(description="묶음 주제, 예: 부모님 욕실 안전템")
    products: List[Product]


SceneKind = Literal["hook", "problem", "solution", "review", "downside", "cta"]


class Scene(BaseModel):
    kind: SceneKind
    product_index: int = Field(0, description="묶음 영상에서 이 장면이 보여줄 상품 순서(0부터). 단품은 0")
    narration: str = Field(description="TTS로 읽을 문장. 친근하고 빠른 말투, 짧은 문장")
    captions: List[str] = Field(
        description="narration을 순서대로 잘게 나눈 자막 조각. 조각마다 12자 이내, 이어 붙이면 narration 내용과 같아야 함"
    )


class ShortScript(BaseModel):
    product_name: str
    top_title: str = Field(description="영상 내내 상단에 고정되는 2줄 제목. 줄마다 11자 이내, 줄바꿈은 \\n")
    title: str = Field(description="유튜브 제목, 40자 이내, #shorts 제외")
    description: str = Field(description="설명란. 첫 줄 광고 고지, 이어서 '번호. 상품명' 목록")
    pinned_comment: str = Field(description="고정 댓글용 문구: 번호별 상품명과 '프로필 링크에서 번호로 찾으세요'")
    hashtags: List[str]
    scenes: List[Scene]
    source_notes: List[str] = Field(description="후기·단점의 근거가 된 출처 요약(검수용, 영상에 안 나감)")
    approved: bool = Field(False, description="사람이 검수 후 true로 바꾼다")
