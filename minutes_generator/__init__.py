# -*- coding: utf-8 -*-
"""모의 이사회 의사록 생성기.

sample(seed) 하나로 본문 텍스트와 정답셋(JSON)을 함께 얻는다.
"""

from .agenda import GENERATORS, WEIGHTS
from .generator import build_minutes
from .model import Minutes, Style
from .render import ground_truth, render_text

__all__ = [
    "build_minutes", "render_text", "ground_truth", "sample",
    "GENERATORS", "WEIGHTS", "Minutes", "Style",
]

__version__ = "0.1.0"


def sample(seed=None, agenda_kinds=None, n_agenda=None):
    """(본문 텍스트, 정답셋 dict)를 돌려준다."""
    minutes = build_minutes(seed=seed, agenda_kinds=agenda_kinds, n_agenda=n_agenda)
    gt = ground_truth(minutes)
    gt["seed"] = seed
    return render_text(minutes, seed or 0), gt
