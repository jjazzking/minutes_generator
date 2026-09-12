# -*- coding: utf-8 -*-
"""이미지 잡음 생성 도우미.

Pillow 의 Image.effect_noise 는 내부 난수를 쓰기 때문에 시드를 고정해도 결과가 달라진다.
벤치마크는 같은 시드에서 같은 이미지가 나와야 하므로 난수를 직접 만들어 쓴다.
"""

import random
from typing import Tuple

# 균등분포 두 장을 섞으면 삼각분포가 되고, 그 표준편차는 대략 이 값이다.
_TRIANGULAR_SIGMA = 52.2


def noise_layer(size: Tuple[int, int], sigma: float, rng: random.Random):
    """평균 128, 표준편차 sigma 인 L 모드 잡음 이미지."""
    from PIL import Image, ImageChops

    width, height = size
    count = width * height
    first = Image.frombytes("L", size, _randbytes(rng, count))
    second = Image.frombytes("L", size, _randbytes(rng, count))
    layer = ImageChops.blend(first, second, 0.5)
    scale = sigma / _TRIANGULAR_SIGMA
    if abs(scale - 1.0) > 1e-3:
        table = [max(0, min(255, int(128 + (v - 128) * scale))) for v in range(256)]
        layer = layer.point(table)
    return layer


def _randbytes(rng: random.Random, count: int) -> bytes:
    try:
        return rng.randbytes(count)            # Python 3.9 이상
    except AttributeError:
        return bytes(rng.getrandbits(8) for _ in range(count))
