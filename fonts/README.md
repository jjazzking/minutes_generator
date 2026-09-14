# fonts/

여기에 둔 한글 글꼴을 `minutes_generator/fonts.py` 가 **운영체제 기본 글꼴보다
먼저** 찾아 씁니다. 글꼴을 동봉해 두면 macOS / Windows / Linux 어디서 실행해도
결과가 같고, 글꼴이 PDF 에 임베드되어 보는 환경을 타지 않습니다.

찾는 파일명 (없으면 그냥 건너뜁니다):

| 용도 | 파일명 |
| --- | --- |
| 고딕 본문 | `NanumGothic.ttf` 또는 `NotoSansKR-Regular.ttf` |
| 고딕 굵게 | `NanumGothicBold.ttf` 또는 `NotoSansKR-Bold.ttf` |
| 명조 본문 | `NanumMyeongjo.ttf` 또는 `NotoSerifKR-Regular.ttf` |
| 명조 굵게 | `NanumMyeongjoBold.ttf` 또는 `NotoSerifKR-Bold.ttf` |

환경변수 `MINUTES_FONT_GOTHIC` / `MINUTES_FONT_MYEONGJO` / `MINUTES_FONT_BOLD`
로 지정한 글꼴은 여기 있는 글꼴보다도 우선합니다.

## 주의: 반드시 TrueType(.ttf) 이어야 합니다

reportlab 은 TrueType 아웃라인(`glyf` 테이블)만 읽습니다. PostScript/CFF
아웃라인을 쓰는 OpenType 글꼴(파일 시작 4바이트가 `OTTO`, 보통 `.otf`)을 넣으면
PDF 출력에서 이렇게 실패합니다:

```
TTFError: ... postscript outlines are not supported
```

macOS 기본 한글 글꼴 `/System/Library/Fonts/AppleSDGothicNeo.ttc` 와
Google Fonts 의 "Noto Sans KR" 기본 배포본(`.otf`)이 여기에 해당합니다.
`fonts.py` 가 이런 글꼴을 PDF 경로에서 자동으로 걸러내긴 하지만, 애초에 TTF 를
넣는 편이 좋습니다. 나눔글꼴 TTF 는 https://hangeul.naver.com/font 에서 받습니다.

지금 어떤 글꼴이 잡히는지, 무엇이 CFF 라서 제외됐는지 확인:

```bash
python -m minutes_generator --check-fonts
```
