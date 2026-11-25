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
    idea: Optional[dict] = Field(None, description="ideas 단계가 붙인 아이디어(각도·훅·장면·형식). 대본이 이를 따른다")
    status: str = Field("approved", description="candidate(검토 전) | approved")
    bgm: Optional[str] = Field(None, description="배경음악: 분위기 폴더(bright/calm/funny), 파일 경로, 또는 none")


class Bundle(BaseModel):
    """TOP3 묶음 영상용. products/*.json 에 {"slug": ..., "products": [...]} 형태로 둔다."""

    slug: str
    theme: str = Field(description="묶음 주제, 예: 부모님 욕실 안전템")
    products: List[Product]
    bgm: Optional[str] = None


SceneKind = Literal["hook", "problem", "solution", "review", "downside", "cta"]


class Scene(BaseModel):
    kind: SceneKind
    product_index: int = Field(0, description="묶음 영상에서 이 장면이 보여줄 상품 순서(0부터). 단품은 0")
    narration: str = Field(description="TTS로 읽을 문장. 친근하고 빠른 말투, 짧은 문장")
    shot: Optional[int] = Field(None, description="ai 스토리 형식: 이 장면에 보여줄 컷 번호(1부터, ai_shots 순서). cta는 비움")
    captions: List[str] = Field(
        description="narration을 순서대로 잘게 나눈 자막 조각. 조각마다 12자 이내, 이어 붙이면 narration 내용과 같아야 함"
    )


class ShortScript(BaseModel):
    format: Literal["slides", "aiimage", "ai", "list"] = Field(
        "slides", description="slides: 사진 전환형, aiimage: AI 장면 이미지, ai: AI 영상 장면, list: 필수템 번호 목록")
    product_name: str
    top_title: str = Field(description="영상 내내 상단에 고정되는 2줄 제목. 줄마다 11자 이내, 줄바꿈은 \\n")
    title: str = Field(description="유튜브 제목, 40자 이내, #shorts 제외")
    description: str = Field(description="설명란. 첫 줄 광고 고지, 이어서 '번호. 상품명' 목록")
    pinned_comment: str = Field(description="고정 댓글용 문구: 번호별 상품명과 '프로필 링크에서 번호로 찾으세요'")
    hashtags: List[str]
    scenes: List[Scene]
    list_items: Optional[List[str]] = Field(
        None, description="list 형식일 때만: '번호. 상품 한 줄' 8~10개. 번호는 상품의 link_no와 같게, 한 줄 14자 이내"
    )
    ai_image_prompts: Optional[List[str]] = Field(
        None, description="aiimage 형식일 때만: AI 장면 이미지 3~4장의 영어 설명 (hook·problem·solution 순서)"
    )
    ai_prompt: Optional[str] = Field(
        None, description="ai 형식일 때만: AI 영상 모델에 줄 영어 장면 설명 (8초, 한 장면, 어르신이 상품을 쓰는 일상)"
    )
    ai_shots: Optional[List[str]] = Field(
        None, description="ai 형식 스토리 컷(2~3개)의 영어 Flow 프롬프트. 컷마다 같은 인물 설명을 반복"
    )
    source_notes: List[str] = Field(description="후기·단점의 근거가 된 출처 요약(검수용, 영상에 안 나감)")
    approved: bool = Field(False, description="사람이 검수 후 true로 바꾼다")


AngleKind = Literal["반전", "후회", "상황극", "비교", "리스트"]


class Idea(BaseModel):
    slug: str = Field(description="영문 소문자-하이픈 식별자, 예: knee-free-dustpan")
    product_name: str = Field(description="검색에 쓸 일반 상품명 (브랜드 X)")
    category: str
    price_range: str = Field(description="예: 1만 원대")
    why_sells: str = Field(description="왜 쇼츠로 팔릴지 한두 문장")
    angle: AngleKind
    hook: str = Field(description="첫 1~2초 말풍선/내레이션 한 줄, 어르신에게 말하는 말투")
    top_title: str = Field(description="상단 고정 2줄 제목, 줄마다 11자 이내, 줄바꿈 \\n")
    scene: str = Field(description="화면 아이디어(한국어): 어떤 장면을 보여줄지")
    format: Literal["ai", "aiimage", "list"]
    coupang_keyword: str = Field(description="쿠팡 파트너스 링크 생성 화면에서 이 상품을 찾을 검색어 (짧고 일반적인 상품명)")
    evidence: str = Field(description="인기 근거(리뷰 수·판매 순위·출처 URL 등)")
    risk_notes: str = Field(description="광고·정책·효능 문구 위험, 영상 표현 어려움 등")


class IdeaBatch(BaseModel):
    ideas: List[Idea]
