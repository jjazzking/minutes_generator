# fonts/

한글 폰트 파일(TTF)을 여기에 넣으면 `fonts.py` 가 가장 먼저 찾아 씁니다.
여기에 폰트가 있으면 macOS / Windows / Linux 어디서 실행해도 결과가 같고,
글꼴이 PDF 에 임베드되어 뷰어 환경을 타지 않습니다.

권장 파일명 (`fonts.py` 의 후보 목록과 일치):

- `NanumGothic.ttf`, `NanumGothicBold.ttf`
- 또는 `NotoSansKR-Regular.ttf`, `NotoSansKR-Bold.ttf`

## 주의: 반드시 TrueType(.ttf) 이어야 합니다

ReportLab 은 TrueType 아웃라인(`glyf`)만 읽습니다. PostScript/CFF 아웃라인을
쓰는 OpenType 폰트(파일 시작이 `OTTO`, 보통 `.otf`)를 넣으면 이런 에러가 납니다:

```
TTFError: ... postscript outlines are not supported
```

macOS 기본 한글 폰트 `/System/Library/Fonts/AppleSDGothicNeo.ttc` 와
Google Fonts 의 "Noto Sans KR" 기본 배포본(.otf)이 여기에 해당하니 쓰지 마세요.
나눔고딕 TTF 는 https://hangeul.naver.com/font 에서 받을 수 있습니다.

폰트 파일을 확인하는 법:

```bash
head -c 4 fonts/NanumGothic.ttf   # OTTO 가 나오면 CFF 라서 못 씁니다
```

폰트를 하나도 못 찾으면 `fonts.py` 는 ReportLab 내장 CID 폰트
(`HYSMyeongJo-Medium`)로 자동 폴백하므로 실행이 실패하지는 않습니다.
